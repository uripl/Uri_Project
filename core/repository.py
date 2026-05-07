from __future__ import annotations

from datetime import date, datetime

from core.db import get_store
from core.models import (
    CashEvent,
    Debt,
    ExpectedIncome,
    RecurringExpense,
    Tenant,
)


def _serialize_value(value):
    """Convert a Python value to its row-cell representation."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _serialize_fields(fields: dict) -> dict:
    return {k: _serialize_value(v) for k, v in fields.items()}


# Tenants ----------------------------------------------------------------------

def list_tenants() -> list[Tenant]:
    rows = get_store().list_rows(Tenant.TABLE)
    tenants = [Tenant.from_row(r) for r in rows]
    tenants.sort(key=lambda t: t.name)
    return tenants


def get_tenant(tenant_id: int) -> Tenant | None:
    row = get_store().get_row(Tenant.TABLE, tenant_id)
    return Tenant.from_row(row) if row is not None else None


def create_tenant(name: str, currency: str = "ILS", opening_balance: float = 0.0,
                  notes: str | None = None) -> Tenant:
    tenant = Tenant(
        id=0, name=name, currency=currency,
        opening_balance=opening_balance, notes=notes,
        created_at=datetime.now(),
    )
    row = tenant.to_row()
    row.pop("id", None)
    inserted = get_store().insert(Tenant.TABLE, row)
    return Tenant.from_row(inserted)


def update_tenant(tenant_id: int, **fields) -> None:
    if not fields:
        return
    if get_tenant(tenant_id) is None:
        raise ValueError(f"Tenant {tenant_id} not found")
    get_store().update(Tenant.TABLE, tenant_id, _serialize_fields(fields))


def delete_tenant(tenant_id: int) -> None:
    store = get_store()
    for table in (Debt.TABLE, ExpectedIncome.TABLE, RecurringExpense.TABLE, CashEvent.TABLE):
        store.delete_where(table, {"tenant_id": tenant_id})
    store.delete(Tenant.TABLE, tenant_id)


# Debts ------------------------------------------------------------------------

def list_debts(tenant_id: int, only_open: bool = False) -> list[Debt]:
    rows = get_store().list_rows(Debt.TABLE)
    debts = [Debt.from_row(r) for r in rows if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if only_open:
        debts = [d for d in debts if d.status != "paid"]
    debts.sort(key=lambda d: d.due_date)
    return debts


def get_debt(tenant_id: int, debt_id: int) -> Debt | None:
    row = get_store().get_row(Debt.TABLE, debt_id)
    if row is None:
        return None
    debt = Debt.from_row(row)
    return debt if debt.tenant_id == tenant_id else None


def create_debt(tenant_id: int, **fields) -> Debt:
    debt = Debt(id=0, tenant_id=tenant_id, creditor="", created_at=datetime.now())
    for k, v in fields.items():
        setattr(debt, k, v)
    row = debt.to_row()
    row.pop("id", None)
    inserted = get_store().insert(Debt.TABLE, row)
    return Debt.from_row(inserted)


def update_debt(tenant_id: int, debt_id: int, **fields) -> None:
    if get_debt(tenant_id, debt_id) is None:
        raise ValueError("Debt not found for this tenant")
    get_store().update(Debt.TABLE, debt_id, _serialize_fields(fields))


def delete_debt(tenant_id: int, debt_id: int) -> None:
    if get_debt(tenant_id, debt_id) is None:
        return
    get_store().delete(Debt.TABLE, debt_id)


def mark_debt_paid(tenant_id: int, debt_id: int, payment_date: date | None = None) -> None:
    debt = get_debt(tenant_id, debt_id)
    if debt is None:
        raise ValueError("Debt not found for this tenant")
    remaining = max(debt.original_amount - debt.paid_amount, 0.0)
    update_debt(tenant_id, debt_id, paid_amount=debt.original_amount, status="paid")
    if remaining > 0:
        create_cash_event(
            tenant_id,
            date=payment_date or date.today(),
            direction="out",
            amount=remaining,
            description=f"תשלום חוב: {debt.creditor}",
            source_type="debt_payment",
            source_id=debt.id,
        )


# Expected incomes -------------------------------------------------------------

def list_expected_incomes(tenant_id: int, only_pending: bool = False) -> list[ExpectedIncome]:
    rows = get_store().list_rows(ExpectedIncome.TABLE)
    items = [ExpectedIncome.from_row(r) for r in rows if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if only_pending:
        items = [i for i in items if i.status == "pending"]
    items.sort(key=lambda i: i.expected_date)
    return items


def get_expected_income(tenant_id: int, income_id: int) -> ExpectedIncome | None:
    row = get_store().get_row(ExpectedIncome.TABLE, income_id)
    if row is None:
        return None
    income = ExpectedIncome.from_row(row)
    return income if income.tenant_id == tenant_id else None


def create_expected_income(tenant_id: int, **fields) -> ExpectedIncome:
    income = ExpectedIncome(id=0, tenant_id=tenant_id, source="", created_at=datetime.now())
    for k, v in fields.items():
        setattr(income, k, v)
    row = income.to_row()
    row.pop("id", None)
    inserted = get_store().insert(ExpectedIncome.TABLE, row)
    return ExpectedIncome.from_row(inserted)


def update_expected_income(tenant_id: int, income_id: int, **fields) -> None:
    if get_expected_income(tenant_id, income_id) is None:
        raise ValueError("Income not found for this tenant")
    get_store().update(ExpectedIncome.TABLE, income_id, _serialize_fields(fields))


def delete_expected_income(tenant_id: int, income_id: int) -> None:
    if get_expected_income(tenant_id, income_id) is None:
        return
    get_store().delete(ExpectedIncome.TABLE, income_id)


def mark_income_received(tenant_id: int, income_id: int, received_date: date | None = None) -> None:
    income = get_expected_income(tenant_id, income_id)
    if income is None:
        raise ValueError("Income not found for this tenant")
    update_expected_income(tenant_id, income_id, status="received")
    create_cash_event(
        tenant_id,
        date=received_date or date.today(),
        direction="in",
        amount=income.amount,
        description=f"קבלת הכנסה: {income.source}",
        source_type="income",
        source_id=income.id,
    )


# Recurring expenses -----------------------------------------------------------

def list_recurring_expenses(tenant_id: int, only_active: bool = False) -> list[RecurringExpense]:
    rows = get_store().list_rows(RecurringExpense.TABLE)
    items = [RecurringExpense.from_row(r) for r in rows if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if only_active:
        items = [e for e in items if e.active]
    items.sort(key=lambda e: e.name)
    return items


def get_recurring_expense(tenant_id: int, expense_id: int) -> RecurringExpense | None:
    row = get_store().get_row(RecurringExpense.TABLE, expense_id)
    if row is None:
        return None
    expense = RecurringExpense.from_row(row)
    return expense if expense.tenant_id == tenant_id else None


def create_recurring_expense(tenant_id: int, **fields) -> RecurringExpense:
    expense = RecurringExpense(id=0, tenant_id=tenant_id, name="", created_at=datetime.now())
    for k, v in fields.items():
        setattr(expense, k, v)
    row = expense.to_row()
    row.pop("id", None)
    inserted = get_store().insert(RecurringExpense.TABLE, row)
    return RecurringExpense.from_row(inserted)


def update_recurring_expense(tenant_id: int, expense_id: int, **fields) -> None:
    if get_recurring_expense(tenant_id, expense_id) is None:
        raise ValueError("Expense not found for this tenant")
    get_store().update(RecurringExpense.TABLE, expense_id, _serialize_fields(fields))


def delete_recurring_expense(tenant_id: int, expense_id: int) -> None:
    if get_recurring_expense(tenant_id, expense_id) is None:
        return
    get_store().delete(RecurringExpense.TABLE, expense_id)


# Cash events ------------------------------------------------------------------

def list_cash_events(tenant_id: int, since: date | None = None,
                     until: date | None = None) -> list[CashEvent]:
    rows = get_store().list_rows(CashEvent.TABLE)
    events = [CashEvent.from_row(r) for r in rows if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if since is not None:
        events = [e for e in events if e.date >= since]
    if until is not None:
        events = [e for e in events if e.date <= until]
    events.sort(key=lambda e: e.date)
    return events


def create_cash_event(tenant_id: int, **fields) -> CashEvent:
    event = CashEvent(id=0, tenant_id=tenant_id, created_at=datetime.now())
    for k, v in fields.items():
        setattr(event, k, v)
    row = event.to_row()
    row.pop("id", None)
    inserted = get_store().insert(CashEvent.TABLE, row)
    return CashEvent.from_row(inserted)


def delete_cash_event(tenant_id: int, event_id: int) -> None:
    row = get_store().get_row(CashEvent.TABLE, event_id)
    if row is None:
        return
    if int(row.get("tenant_id", 0) or 0) != tenant_id:
        return
    get_store().delete(CashEvent.TABLE, event_id)


def current_balance(tenant_id: int, as_of: date | None = None) -> float:
    """Opening balance + sum of cash_events (in - out) up to as_of (inclusive)."""
    tenant = get_tenant(tenant_id)
    if tenant is None:
        return 0.0
    events = list_cash_events(tenant_id, until=as_of)
    delta = sum(e.amount if e.direction == "in" else -e.amount for e in events)
    return tenant.opening_balance + delta
