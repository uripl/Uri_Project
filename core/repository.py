from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import (
    CashEvent,
    Debt,
    ExpectedIncome,
    RecurringExpense,
    Tenant,
)


def get_session() -> Session:
    return SessionLocal()


# Tenants ----------------------------------------------------------------------

def list_tenants() -> list[Tenant]:
    with get_session() as s:
        return list(s.scalars(select(Tenant).order_by(Tenant.name)))


def get_tenant(tenant_id: int) -> Tenant | None:
    with get_session() as s:
        return s.get(Tenant, tenant_id)


def create_tenant(name: str, currency: str = "ILS", opening_balance: float = 0.0, notes: str | None = None) -> Tenant:
    with get_session() as s:
        tenant = Tenant(name=name, currency=currency, opening_balance=opening_balance, notes=notes)
        s.add(tenant)
        s.commit()
        s.refresh(tenant)
        return tenant


def update_tenant(tenant_id: int, **fields) -> None:
    with get_session() as s:
        tenant = s.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        for key, value in fields.items():
            setattr(tenant, key, value)
        s.commit()


def delete_tenant(tenant_id: int) -> None:
    with get_session() as s:
        tenant = s.get(Tenant, tenant_id)
        if tenant is not None:
            s.delete(tenant)
            s.commit()


# Debts ------------------------------------------------------------------------

def list_debts(tenant_id: int, only_open: bool = False) -> list[Debt]:
    with get_session() as s:
        stmt = select(Debt).where(Debt.tenant_id == tenant_id).order_by(Debt.due_date)
        if only_open:
            stmt = stmt.where(Debt.status != "paid")
        return list(s.scalars(stmt))


def create_debt(tenant_id: int, **fields) -> Debt:
    with get_session() as s:
        debt = Debt(tenant_id=tenant_id, **fields)
        s.add(debt)
        s.commit()
        s.refresh(debt)
        return debt


def update_debt(tenant_id: int, debt_id: int, **fields) -> None:
    with get_session() as s:
        debt = s.get(Debt, debt_id)
        if debt is None or debt.tenant_id != tenant_id:
            raise ValueError("Debt not found for this tenant")
        for key, value in fields.items():
            setattr(debt, key, value)
        s.commit()


def delete_debt(tenant_id: int, debt_id: int) -> None:
    with get_session() as s:
        debt = s.get(Debt, debt_id)
        if debt is None or debt.tenant_id != tenant_id:
            return
        s.delete(debt)
        s.commit()


def mark_debt_paid(tenant_id: int, debt_id: int, payment_date: date | None = None) -> None:
    with get_session() as s:
        debt = s.get(Debt, debt_id)
        if debt is None or debt.tenant_id != tenant_id:
            raise ValueError("Debt not found for this tenant")
        remaining = max(debt.original_amount - debt.paid_amount, 0.0)
        debt.paid_amount = debt.original_amount
        debt.status = "paid"
        if remaining > 0:
            event = CashEvent(
                tenant_id=tenant_id,
                date=payment_date or date.today(),
                direction="out",
                amount=remaining,
                description=f"תשלום חוב: {debt.creditor}",
                source_type="debt_payment",
                source_id=debt.id,
            )
            s.add(event)
        s.commit()


# Expected incomes -------------------------------------------------------------

def list_expected_incomes(tenant_id: int, only_pending: bool = False) -> list[ExpectedIncome]:
    with get_session() as s:
        stmt = select(ExpectedIncome).where(ExpectedIncome.tenant_id == tenant_id).order_by(ExpectedIncome.expected_date)
        if only_pending:
            stmt = stmt.where(ExpectedIncome.status == "pending")
        return list(s.scalars(stmt))


def create_expected_income(tenant_id: int, **fields) -> ExpectedIncome:
    with get_session() as s:
        income = ExpectedIncome(tenant_id=tenant_id, **fields)
        s.add(income)
        s.commit()
        s.refresh(income)
        return income


def update_expected_income(tenant_id: int, income_id: int, **fields) -> None:
    with get_session() as s:
        income = s.get(ExpectedIncome, income_id)
        if income is None or income.tenant_id != tenant_id:
            raise ValueError("Income not found for this tenant")
        for key, value in fields.items():
            setattr(income, key, value)
        s.commit()


def delete_expected_income(tenant_id: int, income_id: int) -> None:
    with get_session() as s:
        income = s.get(ExpectedIncome, income_id)
        if income is None or income.tenant_id != tenant_id:
            return
        s.delete(income)
        s.commit()


def mark_income_received(tenant_id: int, income_id: int, received_date: date | None = None) -> None:
    with get_session() as s:
        income = s.get(ExpectedIncome, income_id)
        if income is None or income.tenant_id != tenant_id:
            raise ValueError("Income not found for this tenant")
        income.status = "received"
        event = CashEvent(
            tenant_id=tenant_id,
            date=received_date or date.today(),
            direction="in",
            amount=income.amount,
            description=f"קבלת הכנסה: {income.source}",
            source_type="income",
            source_id=income.id,
        )
        s.add(event)
        s.commit()


# Recurring expenses -----------------------------------------------------------

def list_recurring_expenses(tenant_id: int, only_active: bool = False) -> list[RecurringExpense]:
    with get_session() as s:
        stmt = select(RecurringExpense).where(RecurringExpense.tenant_id == tenant_id).order_by(RecurringExpense.name)
        if only_active:
            stmt = stmt.where(RecurringExpense.active.is_(True))
        return list(s.scalars(stmt))


def create_recurring_expense(tenant_id: int, **fields) -> RecurringExpense:
    with get_session() as s:
        expense = RecurringExpense(tenant_id=tenant_id, **fields)
        s.add(expense)
        s.commit()
        s.refresh(expense)
        return expense


def update_recurring_expense(tenant_id: int, expense_id: int, **fields) -> None:
    with get_session() as s:
        expense = s.get(RecurringExpense, expense_id)
        if expense is None or expense.tenant_id != tenant_id:
            raise ValueError("Expense not found for this tenant")
        for key, value in fields.items():
            setattr(expense, key, value)
        s.commit()


def delete_recurring_expense(tenant_id: int, expense_id: int) -> None:
    with get_session() as s:
        expense = s.get(RecurringExpense, expense_id)
        if expense is None or expense.tenant_id != tenant_id:
            return
        s.delete(expense)
        s.commit()


# Cash events ------------------------------------------------------------------

def list_cash_events(tenant_id: int, since: date | None = None, until: date | None = None) -> list[CashEvent]:
    with get_session() as s:
        stmt = select(CashEvent).where(CashEvent.tenant_id == tenant_id).order_by(CashEvent.date)
        if since is not None:
            stmt = stmt.where(CashEvent.date >= since)
        if until is not None:
            stmt = stmt.where(CashEvent.date <= until)
        return list(s.scalars(stmt))


def create_cash_event(tenant_id: int, **fields) -> CashEvent:
    with get_session() as s:
        event = CashEvent(tenant_id=tenant_id, **fields)
        s.add(event)
        s.commit()
        s.refresh(event)
        return event


def delete_cash_event(tenant_id: int, event_id: int) -> None:
    with get_session() as s:
        event = s.get(CashEvent, event_id)
        if event is None or event.tenant_id != tenant_id:
            return
        s.delete(event)
        s.commit()


def current_balance(tenant_id: int, as_of: date | None = None) -> float:
    """Opening balance + sum of cash_events (in - out) up to as_of (inclusive)."""
    tenant = get_tenant(tenant_id)
    if tenant is None:
        return 0.0
    events = list_cash_events(tenant_id, until=as_of)
    delta = sum(e.amount if e.direction == "in" else -e.amount for e in events)
    return tenant.opening_balance + delta
