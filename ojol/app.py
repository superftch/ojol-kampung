import asyncio
import json
import os
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .controller import Controller, StopRequested
from .healing import write_private
from .http_core import HttpUI
from .journal import Journal
from .models import Settings, now
from .planner import next_step
from .reconciliation import reconcile, wait_until_resolved


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
                    await reconcile(ui, journal)
                    if journal.unresolved():
                        print(
                            "Masih ada hasil aksi yang belum pasti. Periksa riwayat sebelum melanjutkan."
                        )
                    else:
                        print(
                            "Riwayat yang tersedia sudah sesuai game. Tekan Jalankan Ojol untuk melanjutkan."
                        )
                finally:
                    journal.close()
            else:
                journal = Journal(self.settings.runtime_dir)
                try:
                    if self.live:
                        write_private(
                            self.settings.runtime_dir / "status.json",
                            {
                                "pid": os.getpid(),
                                "event": "rekonsiliasi",
                                "stage": "worker.reconcile",
                                "time": now().isoformat(),
                            },
                        )
                        reconciled = await wait_until_resolved(ui, journal, self.settings)
                    else:
                        reconciled = await ui.snapshot()
                    run_id = journal.start(self.settings)
                except BaseException:
                    journal.close()
                    raise
                controller = Controller(ui, self.settings, journal, run_id, self.cancel)
                controller.state = reconciled
                controller.snapshot_received_at = now().isoformat()
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
                    await controller.run(
                        dry_run=not self.live,
                        auto_start=self.live and os.environ.get("OJOL_WORKER_AUTO_START") == "1",
                    )
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
