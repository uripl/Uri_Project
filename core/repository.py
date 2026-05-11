from __future__ import annotations

from datetime import date, datetime, timedelta

from core.db import get_store
from core.models import (
    CashEvent,
    Debt,
    DebtInstallment,
    ExpectedIncome,
    RecurringExpense,
    RecurringIncome,
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
    for table in (Debt.TABLE, DebtInstallment.TABLE, ExpectedIncome.TABLE,
                  RecurringExpense.TABLE, RecurringIncome.TABLE, CashEvent.TABLE):
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
    # Cascade: remove any installments tied to this debt.
    get_store().delete_where(DebtInstallment.TABLE, {"debt_id": debt_id})
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


# Debt installments ------------------------------------------------------------

def list_debt_installments(tenant_id: int, debt_id: int | None = None,
                           only_pending: bool = False) -> list[DebtInstallment]:
    rows = get_store().list_rows(DebtInstallment.TABLE)
    items = [DebtInstallment.from_row(r) for r in rows
             if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if debt_id is not None:
        items = [i for i in items if i.debt_id == debt_id]
    if only_pending:
        items = [i for i in items if i.status != "paid"]
    items.sort(key=lambda i: i.due_date)
    return items


def get_debt_installment(tenant_id: int, installment_id: int) -> DebtInstallment | None:
    row = get_store().get_row(DebtInstallment.TABLE, installment_id)
    if row is None:
        return None
    inst = DebtInstallment.from_row(row)
    return inst if inst.tenant_id == tenant_id else None


def create_debt_installment(tenant_id: int, debt_id: int, **fields) -> DebtInstallment:
    inst = DebtInstallment(id=0, tenant_id=tenant_id, debt_id=debt_id,
                            created_at=datetime.now())
    for k, v in fields.items():
        setattr(inst, k, v)
    row = inst.to_row()
    row.pop("id", None)
    inserted = get_store().insert(DebtInstallment.TABLE, row)
    return DebtInstallment.from_row(inserted)


def update_debt_installment(tenant_id: int, installment_id: int, **fields) -> None:
    if get_debt_installment(tenant_id, installment_id) is None:
        raise ValueError("Installment not found for this tenant")
    get_store().update(DebtInstallment.TABLE, installment_id, _serialize_fields(fields))


def delete_debt_installment(tenant_id: int, installment_id: int) -> None:
    if get_debt_installment(tenant_id, installment_id) is None:
        return
    get_store().delete(DebtInstallment.TABLE, installment_id)


def mark_installment_paid(tenant_id: int, installment_id: int,
                          payment_date: date | None = None) -> None:
    inst = get_debt_installment(tenant_id, installment_id)
    if inst is None:
        raise ValueError("Installment not found for this tenant")
    update_debt_installment(tenant_id, installment_id, status="paid")
    debt = get_debt(tenant_id, inst.debt_id)
    if debt is not None:
        new_paid = min(debt.paid_amount + inst.amount, debt.original_amount)
        new_status = "paid" if new_paid >= debt.original_amount - 0.01 else debt.status
        update_debt(tenant_id, debt.id, paid_amount=new_paid, status=new_status)
    create_cash_event(
        tenant_id,
        date=payment_date or date.today(),
        direction="out",
        amount=inst.amount,
        description=f"תשלום הסדר על חוב #{inst.debt_id}",
        source_type="installment_payment",
        source_id=inst.id,
    )


def schedule_installments(tenant_id: int, debt_id: int, count: int,
                          first_date: date, frequency: str = "monthly",
                          replace_existing: bool = True) -> list[DebtInstallment]:
    """Generate `count` equal installments for the remaining balance of a debt,
    starting at `first_date`. If `replace_existing`, any pending installments
    for this debt are deleted first."""
    debt = get_debt(tenant_id, debt_id)
    if debt is None:
        raise ValueError("Debt not found")
    remaining = max(debt.original_amount - debt.paid_amount, 0.0)
    if count < 1 or remaining <= 0:
        return []
    if replace_existing:
        store = get_store()
        existing = list_debt_installments(tenant_id, debt_id, only_pending=True)
        for inst in existing:
            store.delete(DebtInstallment.TABLE, inst.id)

    per_payment = round(remaining / count, 2)
    installments: list[DebtInstallment] = []
    cur = first_date
    for i in range(count):
        amount = per_payment if i < count - 1 else round(remaining - per_payment * (count - 1), 2)
        inst = create_debt_installment(
            tenant_id, debt_id,
            due_date=cur,
            amount=amount,
            status="scheduled",
        )
        installments.append(inst)
        if frequency == "monthly":
            month = cur.month + 1
            year = cur.year + (1 if month > 12 else 0)
            month = ((month - 1) % 12) + 1
            day = min(cur.day, _last_day_of_month(year, month))
            cur = date(year, month, day)
        elif frequency == "weekly":
            cur = cur + timedelta(days=7)
        else:
            cur = date(cur.year, cur.month, cur.day)
    return installments


def _last_day_of_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


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


# Recurring incomes ------------------------------------------------------------

def list_recurring_incomes(tenant_id: int, only_active: bool = False) -> list[RecurringIncome]:
    rows = get_store().list_rows(RecurringIncome.TABLE)
    items = [RecurringIncome.from_row(r) for r in rows if int(r.get("tenant_id", 0) or 0) == tenant_id]
    if only_active:
        items = [i for i in items if i.active]
    items.sort(key=lambda i: i.source)
    return items


def get_recurring_income(tenant_id: int, income_id: int) -> RecurringIncome | None:
    row = get_store().get_row(RecurringIncome.TABLE, income_id)
    if row is None:
        return None
    income = RecurringIncome.from_row(row)
    return income if income.tenant_id == tenant_id else None


def create_recurring_income(tenant_id: int, **fields) -> RecurringIncome:
    income = RecurringIncome(id=0, tenant_id=tenant_id, source="", created_at=datetime.now())
    for k, v in fields.items():
        setattr(income, k, v)
    row = income.to_row()
    row.pop("id", None)
    inserted = get_store().insert(RecurringIncome.TABLE, row)
    return RecurringIncome.from_row(inserted)


def update_recurring_income(tenant_id: int, income_id: int, **fields) -> None:
    if get_recurring_income(tenant_id, income_id) is None:
        raise ValueError("Recurring income not found for this tenant")
    get_store().update(RecurringIncome.TABLE, income_id, _serialize_fields(fields))


def delete_recurring_income(tenant_id: int, income_id: int) -> None:
    if get_recurring_income(tenant_id, income_id) is None:
        return
    get_store().delete(RecurringIncome.TABLE, income_id)


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


def get_cash_event(tenant_id: int, event_id: int) -> CashEvent | None:
    row = get_store().get_row(CashEvent.TABLE, event_id)
    if row is None:
        return None
    event = CashEvent.from_row(row)
    return event if event.tenant_id == tenant_id else None


def update_cash_event(tenant_id: int, event_id: int, **fields) -> None:
    if get_cash_event(tenant_id, event_id) is None:
        raise ValueError("Event not found for this tenant")
    get_store().update(CashEvent.TABLE, event_id, _serialize_fields(fields))


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
