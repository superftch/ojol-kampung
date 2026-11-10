from decimal import Decimal

from ojol.finance import received_income
from ojol.journal import Journal
from ojol.models import Product
from ojol.planner import select_product


def test_income_is_received_payout_not_wallet_or_gross_fare(state):
    before = state.model_copy(update={"trip": "ongkos 0,8 koin"})
    after = state.model_copy(
        update={"wallet": state.wallet + 100, "history": ["19.00 A → B · +0,72", *state.history]}
    )
    amount, entries = received_income(before, after)
    assert amount == Decimal("0.72") and len(entries) == 1


def test_missing_income_evidence_stays_unknown(state):
    assert received_income(state, state.model_copy(update={"wallet": state.wallet + 1})) is None


def test_identical_history_rows_still_count_new_occurrence(state):
    entry = "19.00 A → B · +0,72"
    before = state.model_copy(update={"history": [entry, *state.history]})
    after = state.model_copy(update={"history": [entry, *before.history]})
    assert received_income(before, after)[0] == Decimal("0.72")


def test_income_decimal_sum_and_no_repeat_history(state):
    after = state.model_copy(
        update={"history": ["19.01 A → C · +0,1", "19.00 A → B · +0,2", *state.history]}
    )
    assert received_income(state, after)[0] == Decimal("0.3")


def test_income_expenses_net_persist_and_never_double_book(settings, state):
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    after_trip = state.model_copy(
        update={
            "wallet": state.wallet + Decimal("0.72"),
            "history": ["19.00 A → B · +0,72", *state.history],
        }
    )
    claim = journal.begin(run, "complete", state, {"label": "Sampai"})
    journal.settle(claim, True, after_trip)
    journal.settle(claim, True, after_trip)
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    purchase = journal.begin(
        run,
        "purchase",
        after_trip,
        {"resource": "data", "shop": "Fixture", "product": product.model_dump(mode="json")},
    )
    journal.settle(
        purchase,
        True,
        after_trip.model_copy(update={"wallet": after_trip.wallet - Decimal("0.5"), "data": 86}),
    )
    profit = journal.profit(run)
    assert profit["pendapatan_ojol"] == "0.72" and profit["pengeluaran"] == "0.5"
    assert profit["laba_bersih"] == "0.22" and profit["biaya_per_kategori"] == {"data": "0.5"}
    assert profit["trip_tercatat"] == 1 and profit["pembelian_tercatat"] == 1
    journal.close()
    reopened = Journal(settings.runtime_dir)
    assert reopened.profit() == profit
    assert len(reopened.financial_report()["transaksi_terakhir"]) == 2
    reopened.close()


def test_pending_or_uncertain_expense_not_treated_as_paid(settings, state):
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    action = journal.begin(
        run, "purchase", state, {"resource": "data", "product": {"price": "0.5"}, "shop": "Fixture"}
    )
    assert journal.profit()["pengeluaran"] == "0"
    journal.settle(action, False)
    assert journal.profit()["pengeluaran"] == "0"
    journal.close()


def test_unlimited_spend_still_honors_cash_reserve(settings, state):
    settings = settings.model_copy(update={"max_spend": None, "min_balance": Decimal(20)})
    products = [
        Product(
            name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
        )
    ]
    assert select_product(state, "data", products, settings, Decimal(9999)) is not None
    assert (
        select_product(
            state.model_copy(update={"wallet": Decimal("20.49")}),
            "data",
            products,
            settings,
            Decimal(0),
        )
        is None
    )
    assert (
        select_product(
            state.model_copy(update={"wallet": Decimal("20.51")}),
            "data",
            products,
            settings,
            Decimal(0),
        )
        is not None
    )


def test_daily_report_wib_midnight_boundaries_and_decimal(settings, monkeypatch):
    import ojol.journal as module
    from ojol.finance import day_bounds, report_date

    assert day_bounds("2026-11-10") == ("2026-11-09T17:00:00+00:00", "2026-11-10T17:00:00+00:00")
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    samples = [
        ("2026-11-09T16:59:59+00:00", "income", "5"),
        ("2026-11-09T17:00:00+00:00", "income", "0.1"),
        ("2026-11-10T16:59:58+00:00", "income", "0.2"),
        ("2026-11-10T16:59:59+00:00", "expense", "0.05"),
        ("2026-11-10T17:00:00+00:00", "income", "9"),
    ]
    with journal.db:
        for index, (stamp, kind, amount) in enumerate(samples):
            journal.db.execute(
                "INSERT INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES(?,?,?,?,?,?,?)",
                (
                    run,
                    f"test:{index}",
                    stamp,
                    kind,
                    "fuel" if kind == "expense" else "ojol",
                    amount,
                    "{}",
                ),
            )
    monkeypatch.setattr(
        module, "report_date", lambda value=None: report_date(value or "2026-11-10")
    )
    report = journal.financial_report()
    assert report["tanggal"] == "2026-11-10" and report["zona_waktu"] == "Asia/Jakarta"
    assert report["total"]["pendapatan_ojol"] == "0.3" and report["total"]["laba_bersih"] == "0.25"
    assert len(report["transaksi_terakhir"]) == 3
    assert report["per_sesi"][0]["laba_bersih"] == "0.25"
    assert journal.financial_report("09-11-2026")["total"]["pendapatan_ojol"] == "5"
    assert journal.financial_report("2026-11-11")["total"]["pendapatan_ojol"] == "9"
    assert journal.financial_report("2026-11-12")["total"]["laba_bersih"] == "0"
    assert journal.financial_report(all_time=True)["total"]["pendapatan_ojol"] == "14.3"
    journal.close()


def test_invalid_cli_report_date_is_rejected_before_touching_worker(settings):
    import pytest

    from ojol.cli import main
    from ojol.models import ROOT

    with pytest.raises(SystemExit) as error:
        main(["--env-file", str(ROOT / ".env.testing"), "profit", "--date", "2026-02-31"])
    assert error.value.code == 2
    assert not (settings.runtime_dir / "STOP").exists()


def test_old_claim_recovers_only_exact_route_minute_and_received_payout(state):
    from datetime import datetime

    from ojol.finance import completion_evidence

    before = state.model_copy(
        update={
            "observed_at": datetime.fromisoformat("2030-01-02T01:10:31+00:00"),
            "phase": "complete",
            "trip": "Antar · ongkos0,8 | 📍 Toko Contoh🏁 Rumah Contoh",
            "today_income": Decimal("3.00"),
            "history": ["08.05 older route · +0,72"],
        }
    )
    after = before.model_copy(
        update={
            "observed_at": datetime.fromisoformat("2030-01-02T01:30:00+00:00"),
            "phase": "idle",
            "wallet": Decimal("29.00"),
            "today_income": Decimal("3.72"),
            "history": [
                "08.10 🧍 Toko Contoh → Rumah Contoh · +0,72",
                *before.history,
            ],
        }
    )
    proof = completion_evidence(before, after)
    assert proof["amount"] == "0.72" and proof["receipt_time_wib"].startswith("2030-01-02T08:10:00")
    for changed in [
        after.model_copy(update={"phase": "complete"}),
        after.model_copy(update={"today_income": Decimal(19)}),
        after.model_copy(
            update={"history": [after.history[0].replace("08.10", "08.25"), *before.history]}
        ),
        after.model_copy(
            update={
                "history": [
                    after.history[0].replace("Toko Contoh", "Other shop"),
                    *before.history,
                ]
            }
        ),
        after.model_copy(update={"history": before.history}),
        after.model_copy(
            update={"history": [after.history[0], "08.15 Other → Other · +0,5", *before.history]}
        ),
    ]:
        assert completion_evidence(before, changed) is None
