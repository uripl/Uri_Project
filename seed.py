"""Seed the database with a demo tenant + realistic sample data."""
from __future__ import annotations

from datetime import date, timedelta

from core import repository as repo
from core.db import init_db


def seed() -> None:
    init_db()

    existing = next((t for t in repo.list_tenants() if t.name == "עסק לדוגמה"), None)
    if existing is not None:
        print(f"Demo tenant already exists (id={existing.id}). Skipping seed.")
        return

    tenant = repo.create_tenant(
        name="עסק לדוגמה",
        currency="ILS",
        opening_balance=18_000.0,
        notes="לקוח דמו - נתונים סינתטיים לבדיקה",
    )
    tid = tenant.id
    today = date.today()

    debts = [
        dict(creditor="ספק חומרי גלם א'", category="ספק", original_amount=22_000, due_date=today - timedelta(days=12)),
        dict(creditor="ספק שירותי ענן", category="ספק", original_amount=4_500, due_date=today + timedelta(days=8)),
        dict(creditor="הלוואת בנק לאומי", category="הלוואה", original_amount=12_000, due_date=today + timedelta(days=20)),
        dict(creditor="מע\"מ רבעון Q1", category="מס", original_amount=15_000, due_date=today + timedelta(days=45)),
        dict(creditor="כרטיס אשראי עסקי", category="כרטיס אשראי", original_amount=7_800, due_date=today + timedelta(days=4)),
        dict(creditor="ספק שיווק", category="ספק", original_amount=3_200, due_date=today - timedelta(days=70)),
    ]
    for d in debts:
        repo.create_debt(tid, **d, paid_amount=0.0, status="open")

    incomes = [
        dict(source="חברת אלפא בע\"מ - חוזה חודשי", amount=14_000, expected_date=today + timedelta(days=10), probability=100),
        dict(source="לקוח בטא - פרויקט", amount=22_000, expected_date=today + timedelta(days=25), probability=80),
        dict(source="לקוח גמא - חשבונית פתוחה", amount=8_500, expected_date=today + timedelta(days=40), probability=70),
        dict(source="חברת אלפא בע\"מ - חוזה חודשי", amount=14_000, expected_date=today + timedelta(days=40), probability=100),
        dict(source="חברת אלפא בע\"מ - חוזה חודשי", amount=14_000, expected_date=today + timedelta(days=70), probability=100),
        dict(source="הצעת מחיר חדשה", amount=18_000, expected_date=today + timedelta(days=60), probability=40),
    ]
    for i in incomes:
        repo.create_expected_income(tid, **i, status="pending")

    recurring = [
        dict(name="שכירות משרד", category="שכירות", amount=6_500, frequency="monthly", day_of_month=1),
        dict(name="משכורות צוות", category="משכורות", amount=24_000, frequency="monthly", day_of_month=9),
        dict(name="חשבונות (חשמל/ארנונה/אינטרנט)", category="קבועות", amount=2_400, frequency="monthly", day_of_month=15),
        dict(name="שירותי הנהלת חשבונות", category="קבועות", amount=1_200, frequency="monthly", day_of_month=20),
    ]
    for e in recurring:
        repo.create_recurring_expense(tid, **e, active=True)

    repo.create_cash_event(
        tid,
        date=today - timedelta(days=3),
        direction="in",
        amount=9_000,
        description="קבלה מלקוח דלתא",
        source_type="manual",
    )
    repo.create_cash_event(
        tid,
        date=today - timedelta(days=1),
        direction="out",
        amount=2_500,
        description="רכש ציוד",
        source_type="manual",
    )

    print(f"Seeded demo tenant '{tenant.name}' (id={tid})")
    print(f"  - {len(debts)} debts")
    print(f"  - {len(incomes)} expected incomes")
    print(f"  - {len(recurring)} recurring expenses")
    print(f"  - 2 manual cash events")


if __name__ == "__main__":
    seed()
