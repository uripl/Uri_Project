from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from core import repository as repo
from core.models import Debt, DebtInstallment, ExpectedIncome, RecurringExpense, RecurringIncome

AGING_BUCKETS = ["0-30", "31-60", "61-90", "90+"]


@dataclass
class CashCurvePoint:
    date: date
    balance: float
    delta_in: float
    delta_out: float


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _generate_recurring_dates(
    item, start: date, end: date
) -> list[date]:
    """Generate occurrence dates for a recurring expense or recurring income
    within [start, end]. Both types share the same `frequency` and `day_of_month`
    semantics."""
    if not item.active:
        return []

    occurrences: list[date] = []

    if item.frequency == "monthly":
        year, month = start.year, start.month
        while True:
            day = min(item.day_of_month or 1, _last_day_of_month(year, month))
            try:
                occ = date(year, month, day)
            except ValueError:
                occ = date(year, month, _last_day_of_month(year, month))
            if occ > end:
                break
            if occ >= start:
                occurrences.append(occ)
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1

    elif item.frequency == "weekly":
        # day_of_month interpreted as weekday: 1=Monday .. 7=Sunday
        target_weekday = ((item.day_of_month or 1) - 1) % 7  # 0=Monday
        cur = start
        while cur.weekday() != target_weekday:
            cur += timedelta(days=1)
            if cur > end:
                return occurrences
        while cur <= end:
            occurrences.append(cur)
            cur += timedelta(days=7)

    return occurrences


def cumulative_cash_curve(
    tenant_id: int,
    start_date: date | None = None,
    horizon_days: int = 365,
) -> pd.DataFrame:
    """Return a daily projected cash balance curve.

    Columns: date, delta_in, delta_out, net, balance.
    """
    if start_date is None:
        start_date = date.today()
    end_date = start_date + timedelta(days=horizon_days)

    opening = repo.current_balance(tenant_id, as_of=start_date)

    debts: list[Debt] = repo.list_debts(tenant_id, only_open=True)
    incomes: list[ExpectedIncome] = repo.list_expected_incomes(tenant_id, only_pending=True)
    expenses: list[RecurringExpense] = repo.list_recurring_expenses(tenant_id, only_active=True)
    recurring_incomes: list[RecurringIncome] = repo.list_recurring_incomes(tenant_id, only_active=True)

    days = pd.date_range(start_date, end_date, freq="D").date
    df = pd.DataFrame({"date": days})
    df["delta_in"] = 0.0
    df["delta_out"] = 0.0

    date_to_idx = {d: i for i, d in enumerate(days)}

    for debt in debts:
        installments = repo.list_debt_installments(tenant_id, debt.id, only_pending=True)
        if installments:
            # Debt has a payment plan: schedule each pending installment.
            # If a scheduled installment's date has already passed (e.g. it was
            # planned for the 1st but today is the 10th), pull it forward to the
            # start of the curve so the planned amount still shows up.
            for inst in installments:
                if inst.due_date < start_date:
                    idx = 0
                elif inst.due_date > end_date:
                    continue
                else:
                    idx = date_to_idx[inst.due_date]
                df.at[idx, "delta_out"] += inst.amount
            continue
        # No plan: only project as a single payment if the due date is still
        # in the future. Past-due debts without a plan are tracked in KPIs but
        # excluded from the cash curve — they're an open obligation the user
        # needs to either mark paid or schedule.
        if debt.due_date < start_date:
            continue
        if debt.due_date > end_date:
            continue
        idx = date_to_idx[debt.due_date]
        df.at[idx, "delta_out"] += max(debt.original_amount - debt.paid_amount, 0.0)

    for income in incomes:
        if income.expected_date < start_date or income.expected_date > end_date:
            continue
        idx = date_to_idx[income.expected_date]
        df.at[idx, "delta_in"] += income.amount * (income.probability / 100.0)

    for expense in expenses:
        for occ in _generate_recurring_dates(expense, start_date, end_date):
            idx = date_to_idx[occ]
            df.at[idx, "delta_out"] += expense.amount

    for ri in recurring_incomes:
        for occ in _generate_recurring_dates(ri, start_date, end_date):
            idx = date_to_idx[occ]
            df.at[idx, "delta_in"] += ri.amount * (ri.probability / 100.0)

    df["net"] = df["delta_in"] - df["delta_out"]
    df["balance"] = opening + df["net"].cumsum()

    return df


def zero_crossing_date(curve_df: pd.DataFrame) -> date | None:
    """First date where balance is <= 0. None if never crosses."""
    if curve_df.empty:
        return None
    negative = curve_df[curve_df["balance"] <= 0]
    if negative.empty:
        return None
    first = negative.iloc[0]["date"]
    if isinstance(first, pd.Timestamp):
        return first.date()
    return first


def positive_recovery_date(curve_df: pd.DataFrame) -> date | None:
    """If the balance is currently negative, the first date it returns to >= 0."""
    if curve_df.empty:
        return None
    if curve_df.iloc[0]["balance"] >= 0:
        return None
    positive = curve_df[curve_df["balance"] >= 0]
    if positive.empty:
        return None
    first = positive.iloc[0]["date"]
    if isinstance(first, pd.Timestamp):
        return first.date()
    return first


def aging_buckets(tenant_id: int, as_of: date | None = None) -> dict[str, float]:
    """Sum of remaining open-debt amounts by overdue bucket (vs as_of)."""
    if as_of is None:
        as_of = date.today()
    debts = repo.list_debts(tenant_id, only_open=True)
    buckets = {b: 0.0 for b in AGING_BUCKETS}
    for debt in debts:
        days_overdue = (as_of - debt.due_date).days
        remaining = max(debt.original_amount - debt.paid_amount, 0.0)
        if remaining <= 0:
            continue
        if days_overdue <= 30:
            buckets["0-30"] += remaining
        elif days_overdue <= 60:
            buckets["31-60"] += remaining
        elif days_overdue <= 90:
            buckets["61-90"] += remaining
        else:
            buckets["90+"] += remaining
    return buckets


def total_open_debt(tenant_id: int) -> float:
    return sum(
        max(d.original_amount - d.paid_amount, 0.0)
        for d in repo.list_debts(tenant_id, only_open=True)
    )


def overdue_debt(tenant_id: int, as_of: date | None = None) -> float:
    if as_of is None:
        as_of = date.today()
    return sum(
        max(d.original_amount - d.paid_amount, 0.0)
        for d in repo.list_debts(tenant_id, only_open=True)
        if d.due_date < as_of
    )


def expected_income_30d(tenant_id: int, as_of: date | None = None) -> float:
    if as_of is None:
        as_of = date.today()
    horizon = as_of + timedelta(days=30)
    one_off = sum(
        i.amount * (i.probability / 100.0)
        for i in repo.list_expected_incomes(tenant_id, only_pending=True)
        if as_of <= i.expected_date <= horizon
    )
    recurring = 0.0
    for ri in repo.list_recurring_incomes(tenant_id, only_active=True):
        for _ in _generate_recurring_dates(ri, as_of, horizon):
            recurring += ri.amount * (ri.probability / 100.0)
    return one_off + recurring


def runway_months(tenant_id: int, as_of: date | None = None) -> float | None:
    """Months until balance crosses 0 based on cumulative curve. None if never."""
    if as_of is None:
        as_of = date.today()
    df = cumulative_cash_curve(tenant_id, start_date=as_of, horizon_days=365)
    crossing = zero_crossing_date(df)
    if crossing is None:
        return None
    days = (crossing - as_of).days
    return max(days / 30.0, 0.0)


def weekly_cash_summary(
    tenant_id: int, start_date: date | None = None, horizon_days: int = 180
) -> pd.DataFrame:
    df = cumulative_cash_curve(tenant_id, start_date=start_date, horizon_days=horizon_days)
    df = df.copy()
    df["period"] = pd.to_datetime(df["date"]).dt.to_period("W-SUN").dt.start_time.dt.date
    grouped = df.groupby("period", as_index=False).agg(
        delta_in=("delta_in", "sum"),
        delta_out=("delta_out", "sum"),
    )
    grouped["net"] = grouped["delta_in"] - grouped["delta_out"]
    return grouped


def monthly_cash_summary(
    tenant_id: int, start_date: date | None = None, horizon_days: int = 365
) -> pd.DataFrame:
    df = cumulative_cash_curve(tenant_id, start_date=start_date, horizon_days=horizon_days)
    df = df.copy()
    df["period"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.start_time.dt.date
    grouped = df.groupby("period", as_index=False).agg(
        delta_in=("delta_in", "sum"),
        delta_out=("delta_out", "sum"),
    )
    grouped["net"] = grouped["delta_in"] - grouped["delta_out"]
    return grouped


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _iter_month_starts(start: date, end: date) -> list[date]:
    """All month-start dates in [start, end], anchored to start.month."""
    y, m = start.year, start.month
    out = []
    while True:
        ms = date(y, m, 1)
        if ms > end:
            break
        out.append(ms)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly_cash_breakdown(
    tenant_id: int, start_date: date | None = None, horizon_days: int = 365
) -> pd.DataFrame:
    """Monthly cash projection split into three categories.

    Columns: period (month-start date), incomes, expenses, debt_payments, net.
    - incomes: one-off expected_incomes + recurring_incomes (probability-weighted).
    - expenses: recurring_expenses only (manual cash events are historical, not forecast).
    - debt_payments: pending installments + bare debts whose due-date lands in the month.
                     Past-due installments (before start_date) collapse into the first month
                     so the planned amount still shows up — matches cumulative_cash_curve.
    """
    if start_date is None:
        start_date = date.today()
    end_date = start_date + timedelta(days=horizon_days)

    debts = repo.list_debts(tenant_id, only_open=True)
    expected_incomes = repo.list_expected_incomes(tenant_id, only_pending=True)
    recurring_expenses = repo.list_recurring_expenses(tenant_id, only_active=True)
    recurring_incomes = repo.list_recurring_incomes(tenant_id, only_active=True)

    months = _iter_month_starts(_month_start(start_date), end_date)
    rows = {ms: {"incomes": 0.0, "expenses": 0.0, "debt_payments": 0.0} for ms in months}
    first_month = months[0] if months else _month_start(start_date)

    def _bucket_for(d: date) -> date | None:
        if d < start_date:
            return first_month
        if d > end_date:
            return None
        return _month_start(d)

    for debt in debts:
        installments = repo.list_debt_installments(tenant_id, debt.id, only_pending=True)
        if installments:
            for inst in installments:
                bucket = _bucket_for(inst.due_date)
                if bucket is None or bucket not in rows:
                    continue
                rows[bucket]["debt_payments"] += inst.amount
            continue
        # No plan: project as single payment only if due date is still in horizon.
        if debt.due_date < start_date or debt.due_date > end_date:
            continue
        rows[_month_start(debt.due_date)]["debt_payments"] += max(
            debt.original_amount - debt.paid_amount, 0.0
        )

    for inc in expected_incomes:
        if inc.expected_date < start_date or inc.expected_date > end_date:
            continue
        rows[_month_start(inc.expected_date)]["incomes"] += inc.amount * (inc.probability / 100.0)

    for exp in recurring_expenses:
        for occ in _generate_recurring_dates(exp, start_date, end_date):
            ms = _month_start(occ)
            if ms in rows:
                rows[ms]["expenses"] += exp.amount

    for ri in recurring_incomes:
        for occ in _generate_recurring_dates(ri, start_date, end_date):
            ms = _month_start(occ)
            if ms in rows:
                rows[ms]["incomes"] += ri.amount * (ri.probability / 100.0)

    df = pd.DataFrame([
        {
            "period": ms,
            "incomes": rows[ms]["incomes"],
            "expenses": rows[ms]["expenses"],
            "debt_payments": rows[ms]["debt_payments"],
            "net": rows[ms]["incomes"] - rows[ms]["expenses"] - rows[ms]["debt_payments"],
        }
        for ms in months
    ])
    return df
