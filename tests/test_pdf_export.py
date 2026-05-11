from datetime import date, timedelta

import pytest

from core import repository as repo
from core.pdf_export import ReportSections, build_cashflow_report


@pytest.fixture
def tenant_with_data():
    t = repo.create_tenant(name="לקוח לדוגמה", opening_balance=20_000.0)
    repo.create_debt(
        t.id, creditor="ספק א'", category="ספק", original_amount=5_000.0,
        paid_amount=0.0, due_date=date.today() + timedelta(days=15), status="open",
    )
    repo.create_expected_income(
        t.id, source="לקוח גדול", amount=8_000.0, probability=80,
        expected_date=date.today() + timedelta(days=10), status="pending",
    )
    repo.create_recurring_expense(
        t.id, name="שכירות", category="שכירות", amount=3_000.0,
        frequency="monthly", day_of_month=1, active=True,
    )
    return t


def test_pdf_export_returns_valid_bytes(tenant_with_data):
    pdf = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=True, monthly=True, debt_matrix=True, events=False),
    )
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    # A trivial report with three sections shouldn't be empty.
    assert len(pdf) > 2_000


def test_pdf_export_respects_section_toggles(tenant_with_data):
    """Disabling all but one section should produce a smaller PDF."""
    full = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=True, monthly=True, debt_matrix=True, events=False),
    )
    kpis_only = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=True, monthly=False, debt_matrix=False, events=False),
    )
    assert len(kpis_only) < len(full)


def test_pdf_export_handles_no_open_debts(tenant_with_data):
    """When no debts are open, the debt-matrix section should still render
    (with an 'no debts' message) and not raise."""
    # Close out the only debt to leave no open debts.
    for d in repo.list_debts(tenant_with_data.id, only_open=True):
        repo.update_debt(tenant_with_data.id, d.id, paid_amount=d.original_amount, status="paid")

    pdf = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=False, monthly=False, debt_matrix=True, events=False),
    )
    assert pdf[:4] == b"%PDF"


def test_pdf_export_with_events_section(tenant_with_data):
    repo.create_cash_event(
        tenant_with_data.id,
        date=date.today(),
        direction="in",
        amount=1_000.0,
        description="תשלום ראשוני",
        source_type="manual",
    )
    pdf = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=False, monthly=False, debt_matrix=False, events=True, events_limit=10),
    )
    assert pdf[:4] == b"%PDF"


def test_pdf_export_with_client_override(tenant_with_data):
    """A custom client name should not crash the report build."""
    pdf = build_cashflow_report(
        tenant_with_data.id,
        sections=ReportSections(kpis=True, monthly=False, debt_matrix=False, events=False),
        client_name_override="עסק החדש בע״מ",
        note="דוח לפגישת הצגת מצב פיננסי",
    )
    assert pdf[:4] == b"%PDF"
