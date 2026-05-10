from datetime import date, timedelta

import pytest

from core import forecast, repository as repo


@pytest.fixture
def tenant():
    return repo.create_tenant(name="Test", opening_balance=10_000.0)


def test_curve_returns_one_row_per_day(tenant):
    today = date.today()
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=30)
    assert len(df) == 31  # inclusive of both endpoints
    assert df["date"].iloc[0] == today
    assert df["date"].iloc[-1] == today + timedelta(days=30)


def test_curve_starts_from_opening_balance_with_no_data(tenant):
    today = date.today()
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=10)
    assert df["balance"].iloc[0] == 10_000.0
    assert (df["balance"] == 10_000.0).all()


def test_curve_subtracts_debt_at_due_date(tenant):
    today = date.today()
    repo.create_debt(
        tenant.id,
        creditor="ספק",
        category="ספק",
        original_amount=3_000.0,
        paid_amount=0.0,
        due_date=today + timedelta(days=5),
        status="open",
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=10)
    assert df.iloc[4]["balance"] == 10_000.0
    assert df.iloc[5]["balance"] == 7_000.0
    assert df.iloc[10]["balance"] == 7_000.0


def test_curve_adds_weighted_expected_income(tenant):
    today = date.today()
    repo.create_expected_income(
        tenant.id,
        source="לקוח",
        amount=5_000.0,
        probability=80,
        expected_date=today + timedelta(days=3),
        status="pending",
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=10)
    assert df.iloc[2]["balance"] == 10_000.0
    assert df.iloc[3]["balance"] == pytest.approx(14_000.0)


def test_curve_applies_monthly_recurring(tenant):
    today = date(2026, 1, 15)
    repo.create_recurring_expense(
        tenant.id,
        name="שכר",
        category="משכורות",
        amount=2_000.0,
        frequency="monthly",
        day_of_month=20,
        active=True,
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=60)
    target1 = (date(2026, 1, 20) - today).days
    target2 = (date(2026, 2, 20) - today).days
    assert df.iloc[target1]["balance"] == 8_000.0
    assert df.iloc[target2]["balance"] == 6_000.0


def test_zero_crossing_when_balance_drops(tenant):
    today = date.today()
    repo.create_debt(
        tenant.id,
        creditor="חוב גדול",
        category="הלוואה",
        original_amount=15_000.0,
        paid_amount=0.0,
        due_date=today + timedelta(days=7),
        status="open",
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=30)
    crossing = forecast.zero_crossing_date(df)
    assert crossing == today + timedelta(days=7)


def test_zero_crossing_returns_none_when_always_positive(tenant):
    today = date.today()
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=30)
    assert forecast.zero_crossing_date(df) is None


def test_aging_buckets_classify_overdue_correctly(tenant):
    today = date.today()
    repo.create_debt(
        tenant.id, creditor="A", category="ספק", original_amount=1_000.0, paid_amount=0.0,
        due_date=today + timedelta(days=10), status="open",
    )
    repo.create_debt(
        tenant.id, creditor="B", category="ספק", original_amount=2_000.0, paid_amount=0.0,
        due_date=today - timedelta(days=15), status="open",
    )
    repo.create_debt(
        tenant.id, creditor="C", category="ספק", original_amount=3_000.0, paid_amount=0.0,
        due_date=today - timedelta(days=45), status="open",
    )
    repo.create_debt(
        tenant.id, creditor="D", category="ספק", original_amount=4_000.0, paid_amount=0.0,
        due_date=today - timedelta(days=120), status="open",
    )
    buckets = forecast.aging_buckets(tenant.id, as_of=today)
    assert buckets["0-30"] == 3_000.0  # A (future, days_overdue<=30) + B (15 days)
    assert buckets["31-60"] == 3_000.0  # C
    assert buckets["61-90"] == 0.0
    assert buckets["90+"] == 4_000.0  # D


def test_paid_debts_excluded_from_aging(tenant):
    today = date.today()
    repo.create_debt(
        tenant.id, creditor="A", category="ספק", original_amount=1_000.0,
        paid_amount=1_000.0, due_date=today - timedelta(days=10), status="paid",
    )
    buckets = forecast.aging_buckets(tenant.id, as_of=today)
    assert sum(buckets.values()) == 0.0


def test_marking_debt_paid_creates_cash_event(tenant):
    today = date.today()
    debt = repo.create_debt(
        tenant.id, creditor="X", category="ספק", original_amount=500.0,
        paid_amount=0.0, due_date=today, status="open",
    )
    assert repo.current_balance(tenant.id) == 10_000.0
    repo.mark_debt_paid(tenant.id, debt.id, payment_date=today)
    assert repo.current_balance(tenant.id) == 9_500.0


def test_overdue_debt_without_plan_is_not_in_curve(tenant):
    today = date.today()
    repo.create_debt(
        tenant.id, creditor="חוב באיחור", category="ספק", original_amount=4_000.0,
        paid_amount=0.0, due_date=today - timedelta(days=20), status="open",
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=30)
    # Without a payment plan, the overdue debt does not get dumped at day 0:
    # it's a known liability without a scheduled payment, so the curve stays flat.
    assert (df["balance"] == 10_000.0).all()


def test_installments_drive_forecast_when_present(tenant):
    today = date.today()
    debt = repo.create_debt(
        tenant.id, creditor="חוב עם הסדר", category="הלוואה", original_amount=6_000.0,
        paid_amount=0.0, due_date=today - timedelta(days=5), status="open",
    )
    repo.create_debt_installment(
        tenant.id, debt.id, due_date=today + timedelta(days=10), amount=2_000.0,
    )
    repo.create_debt_installment(
        tenant.id, debt.id, due_date=today + timedelta(days=40), amount=2_000.0,
    )
    repo.create_debt_installment(
        tenant.id, debt.id, due_date=today + timedelta(days=70), amount=2_000.0,
    )
    df = forecast.cumulative_cash_curve(tenant.id, start_date=today, horizon_days=90)
    # Original due date is ignored; payments hit on installment dates.
    assert df.iloc[9]["balance"] == 10_000.0
    assert df.iloc[10]["balance"] == 8_000.0
    assert df.iloc[40]["balance"] == 6_000.0
    assert df.iloc[70]["balance"] == 4_000.0


def test_schedule_installments_splits_remaining_evenly(tenant):
    today = date.today()
    debt = repo.create_debt(
        tenant.id, creditor="חוב לפריסה", category="ספק", original_amount=12_000.0,
        paid_amount=0.0, due_date=today + timedelta(days=10), status="open",
    )
    plan = repo.schedule_installments(
        tenant.id, debt.id, count=4, first_date=today + timedelta(days=30),
        frequency="monthly",
    )
    assert len(plan) == 4
    assert sum(i.amount for i in plan) == pytest.approx(12_000.0)
    # Each installment is 3000.
    for inst in plan:
        assert inst.amount == pytest.approx(3_000.0)


def test_marking_installment_paid_records_cash_event_and_updates_debt(tenant):
    today = date.today()
    debt = repo.create_debt(
        tenant.id, creditor="X", category="ספק", original_amount=2_000.0,
        paid_amount=0.0, due_date=today + timedelta(days=10), status="open",
    )
    inst = repo.create_debt_installment(
        tenant.id, debt.id, due_date=today, amount=800.0,
    )
    repo.mark_installment_paid(tenant.id, inst.id, payment_date=today)
    refreshed_debt = repo.get_debt(tenant.id, debt.id)
    assert refreshed_debt.paid_amount == pytest.approx(800.0)
    assert repo.current_balance(tenant.id) == 9_200.0


def test_tenants_are_isolated():
    a = repo.create_tenant(name="A", opening_balance=5_000.0)
    b = repo.create_tenant(name="B", opening_balance=8_000.0)

    today = date.today()
    repo.create_debt(
        a.id, creditor="חוב של A", category="ספק", original_amount=1_000.0,
        paid_amount=0.0, due_date=today, status="open",
    )

    a_debts = repo.list_debts(a.id)
    b_debts = repo.list_debts(b.id)
    assert len(a_debts) == 1
    assert len(b_debts) == 0

    assert repo.current_balance(a.id) == 5_000.0
    assert repo.current_balance(b.id) == 8_000.0
