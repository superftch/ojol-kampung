import asyncio
import json
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .controller import Controller, StopRequested
from .finance import completion_evidence
from .http_core import HttpUI
from .journal import Journal
from .models import Settings, Snapshot
from .planner import next_step


class OjolAutomationAgent(BaseAgent):
    settings: Settings
    command: str
    live: bool = False
    shop: str | None = None
    cancel: Any = None

    async def _run_async_impl(self, ctx):
        if self.settings.env == "testing":
            raise ValueError("Agen live tidak boleh dijalankan dalam testing; gunakan mocked UI")
        async with HttpUI(self.settings, ToolContext(ctx)) as ui:

            def check_startup_cancel():
                if (self.cancel and self.cancel.is_set()) or (
                    self.command == "run" and (self.settings.runtime_dir / "STOP").exists()
                ):
                    raise StopRequested("Dihentikan pengguna")

            ui.check_cancel = check_startup_cancel
            ui.check_cancel()
            if self.command in {"inspect", "doctor"}:
                state = await ui.snapshot()
                output = {
                    "mcp": "Ojol HTTP stdio via ADK McpToolset",
                    "core": ui.core_name,
                    "snapshot": state.model_dump(mode="json"),
                    "next": next_step(state, self.settings).model_dump(mode="json"),
                }
                if self.shop:
                    shops = await ui.preview_shops(self.shop)
                    output["shops"] = [
                        {**shop.model_dump(mode="json"), "preferred": shop.preferred}
                        for shop in shops
                    ]
                print(json.dumps(output, ensure_ascii=False, indent=2))
            elif self.command == "reconcile":
                journal = Journal(self.settings.runtime_dir)
                try:
                    pending = [
                        row
                        for row in journal.history(100)["actions"]
                        if row["status"] in {"pending", "uncertain"}
                    ]
                    if not pending:
                        print("Tidak ada aksi tertunda.")
                    for action in pending:
                        before = Snapshot.model_validate_json(action["before_state"])
                        state = await ui.snapshot()
                        if action["kind"] == "search":
                            observed = state
                            await asyncio.sleep(1)
                            state = await ui.snapshot()
                            closed = journal.resolve_search(action["id"], observed, state)
                            if closed:
                                if closed["status"] == "handed_off":
                                    print(
                                        f"Aksi #{action['id']}: pencarian diserahkan ke state {state.phase}; klik tidak diulang, ongkos belum diklaim. Tekan Jalankan Ojol untuk melanjutkan."
                                    )
                                else:
                                    print(
                                        f"Aksi #{action['id']}: ditutup, tidak ada order aktif; klik tidak diulang."
                                    )
                                print(
                                    f"Selisih resource {closed['resource_delta']} dicatat tanpa atribusi penyebab."
                                )
                                if state.wallet != before.wallet:
                                    print(
                                        f"Selisih saldo {closed['wallet_delta']} koin dicatat tanpa atribusi penyebab; tidak dibukukan sebagai pendapatan Ojol."
                                    )
                                continue
                        payload = json.loads(action["payload"])
                        from decimal import Decimal

                        valid = False
                        evidence = None
                        if action["kind"] == "purchase":
                            resource = payload["resource"]
                            valid = getattr(state, resource) > getattr(before, resource) and abs(
                                before.wallet - state.wallet - Decimal(payload["product"]["price"])
                            ) <= Decimal("0.015")
                        elif action["kind"] in {"take", "search"}:
                            valid = state.phase == "delivering"
                        elif action["kind"] == "complete":
                            evidence = completion_evidence(before, state)
                            valid = evidence is not None
                        from .models import now

                        if (now() - before.observed_at).total_seconds() > 300 and not evidence:
                            valid = False
                        if valid:
                            journal.settle(action["id"], True, state)
                            journal.event(
                                action["run_id"],
                                "aksi_dipulihkan_dari_bukti",
                                {"action_id": action["id"], "evidence": evidence},
                            )
                        print(
                            f"Aksi #{action['id']}: "
                            + (
                                "terverifikasi dari state sekarang"
                                if valid
                                else "belum dapat dipastikan; automation tetap diblokir"
                            )
                        )
                        if action["kind"] == "search" and not valid:
                            fields = {
                                "observed_at",
                                "phase",
                                "wallet",
                                "fuel",
                                "condition",
                                "data",
                                "today_income",
                                "trip",
                                "buttons",
                            }
                            print(
                                "Bukti pencarian: "
                                + json.dumps(
                                    {
                                        "before": before.model_dump(mode="json", include=fields),
                                        "current": state.model_dump(mode="json", include=fields),
                                        "history_changed": before.history != state.history,
                                        "observations_stable": observed.model_dump(
                                            exclude={"observed_at"}
                                        )
                                        == state.model_dump(exclude={"observed_at"}),
                                    },
                                    ensure_ascii=False,
                                )
                            )
                finally:
                    journal.close()
            else:
                journal = Journal(self.settings.runtime_dir)
                run_id = journal.start(self.settings)
                controller = Controller(ui, self.settings, journal, run_id, self.cancel)
                ui.check_cancel = controller.check_cancel
                try:
                    controller.report(
                        "mulai",
                        live=self.live,
                        core=ui.core_name,
                        max_spend=str(self.settings.max_spend)
                        if self.settings.max_spend is not None
                        else None,
                        min_balance=str(self.settings.min_balance),
                        max_jobs=self.settings.max_jobs,
                        max_minutes=self.settings.max_minutes,
                    )
                    await controller.run(dry_run=not self.live)
                    journal.finish(run_id, "dry_run")
                except StopRequested as exc:
                    controller.report("berhenti", reason=str(exc))
                    journal.finish(run_id, "stopped")
                except BaseException as exc:
                    from .telegram import redact

                    controller.report(
                        "gagal",
                        category=type(exc).__name__,
                        reason=redact(exc, self.settings),
                        stage=controller.stage,
                        last_action=controller.last_action,
                        core=ui.core_name,
                    )
                    journal.finish(run_id, "error")
                    raise
                finally:
                    journal.close()
        yield Event(author=self.name)


async def run_app(settings, command, live=False, shop=None):
    cancel = asyncio.Event()
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel.set)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="ojol_automation", user_id="local")
    runner = Runner(
        app_name="ojol_automation",
        agent=OjolAutomationAgent(
            name="OjolAutomationAgent",
            settings=settings,
            command=command,
            live=live,
            shop=shop,
            cancel=cancel,
        ),
        session_service=sessions,
    )
    try:
        async for _ in runner.run_async(
            user_id="local",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(text="Jalankan hanya alur Ojol yang dikonfigurasi melalui HTTP MCP.")
                ],
            ),
        ):
            pass
    except StopRequested:
        print("Worker dihentikan sebelum startup selesai.", flush=True)
    finally:
        await runner.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
