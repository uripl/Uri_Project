from datetime import date, datetime


def fmt_currency(amount: float, currency: str = "ILS") -> str:
    sign = "₪" if currency == "ILS" else currency
    if amount is None:
        return "-"
    if amount < 0:
        return f"-{sign}{abs(amount):,.0f}"
    return f"{sign}{amount:,.0f}"


def fmt_currency_precise(amount: float, currency: str = "ILS") -> str:
    sign = "₪" if currency == "ILS" else currency
    if amount is None:
        return "-"
    if amount < 0:
        return f"-{sign}{abs(amount):,.2f}"
    return f"{sign}{amount:,.2f}"


def fmt_date(d: date | datetime | None) -> str:
    if d is None:
        return "-"
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y")


DEBT_CATEGORIES = ["ספק", "הלוואה", "מס", "כרטיס אשראי", "אחר"]
EXPENSE_CATEGORIES = ["שכירות", "משכורות", "קבועות", "תפעול", "אחר"]
INCOME_STATUSES = {"pending": "צפוי", "received": "התקבל", "cancelled": "בוטל"}
DEBT_STATUSES = {"open": "פתוח", "paid": "שולם", "overdue": "באיחור"}
FREQUENCIES = {"monthly": "חודשי", "weekly": "שבועי"}
