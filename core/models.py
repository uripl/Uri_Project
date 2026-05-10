from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%m-%Y")


def _parse_date(value) -> date:
    if value is None or value == "":
        return date.today()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


def _parse_optional_date(value) -> date | None:
    if value is None or value == "":
        return None
    return _parse_date(value)


def _parse_datetime(value) -> datetime:
    if value is None or value == "":
        return datetime.now()
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # Fall back to date-only formats; datetimes are auxiliary metadata, so a
    # graceful fallback to midnight is fine if the cell got truncated by Sheets.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now()


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _parse_int(value, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def _parse_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _parse_optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _parse_optional_str(value) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _date_to_str(d: date | None) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def _dt_to_str(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.isoformat()


@dataclass
class Tenant:
    id: int
    name: str
    currency: str = "ILS"
    opening_balance: float = 0.0
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "tenants"
    HEADERS = ("id", "name", "currency", "opening_balance", "notes", "created_at")

    @classmethod
    def from_row(cls, row: dict) -> "Tenant":
        return cls(
            id=_parse_int(row.get("id")),
            name=str(row.get("name") or ""),
            currency=str(row.get("currency") or "ILS"),
            opening_balance=_parse_float(row.get("opening_balance")),
            notes=_parse_optional_str(row.get("notes")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "currency": self.currency,
            "opening_balance": self.opening_balance,
            "notes": self.notes or "",
            "created_at": _dt_to_str(self.created_at),
        }


@dataclass
class Debt:
    id: int
    tenant_id: int
    creditor: str
    category: str = "ספק"
    original_amount: float = 0.0
    paid_amount: float = 0.0
    due_date: date = field(default_factory=date.today)
    status: str = "open"
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "debts"
    HEADERS = (
        "id", "tenant_id", "creditor", "category", "original_amount",
        "paid_amount", "due_date", "status", "notes", "created_at",
    )

    @classmethod
    def from_row(cls, row: dict) -> "Debt":
        return cls(
            id=_parse_int(row.get("id")),
            tenant_id=_parse_int(row.get("tenant_id")),
            creditor=str(row.get("creditor") or ""),
            category=str(row.get("category") or "ספק"),
            original_amount=_parse_float(row.get("original_amount")),
            paid_amount=_parse_float(row.get("paid_amount")),
            due_date=_parse_date(row.get("due_date")),
            status=str(row.get("status") or "open"),
            notes=_parse_optional_str(row.get("notes")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "creditor": self.creditor,
            "category": self.category,
            "original_amount": self.original_amount,
            "paid_amount": self.paid_amount,
            "due_date": _date_to_str(self.due_date),
            "status": self.status,
            "notes": self.notes or "",
            "created_at": _dt_to_str(self.created_at),
        }

    @property
    def remaining(self) -> float:
        return max(self.original_amount - self.paid_amount, 0.0)


@dataclass
class ExpectedIncome:
    id: int
    tenant_id: int
    source: str
    amount: float = 0.0
    expected_date: date = field(default_factory=date.today)
    probability: int = 100
    status: str = "pending"
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "expected_incomes"
    HEADERS = (
        "id", "tenant_id", "source", "amount", "expected_date",
        "probability", "status", "notes", "created_at",
    )

    @classmethod
    def from_row(cls, row: dict) -> "ExpectedIncome":
        return cls(
            id=_parse_int(row.get("id")),
            tenant_id=_parse_int(row.get("tenant_id")),
            source=str(row.get("source") or ""),
            amount=_parse_float(row.get("amount")),
            expected_date=_parse_date(row.get("expected_date")),
            probability=_parse_int(row.get("probability"), default=100),
            status=str(row.get("status") or "pending"),
            notes=_parse_optional_str(row.get("notes")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source": self.source,
            "amount": self.amount,
            "expected_date": _date_to_str(self.expected_date),
            "probability": self.probability,
            "status": self.status,
            "notes": self.notes or "",
            "created_at": _dt_to_str(self.created_at),
        }

    @property
    def expected_value(self) -> float:
        return self.amount * (self.probability / 100.0)


@dataclass
class RecurringExpense:
    id: int
    tenant_id: int
    name: str
    category: str = "קבועות"
    amount: float = 0.0
    frequency: str = "monthly"
    day_of_month: int = 1
    active: bool = True
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "recurring_expenses"
    HEADERS = (
        "id", "tenant_id", "name", "category", "amount", "frequency",
        "day_of_month", "active", "notes", "created_at",
    )

    @classmethod
    def from_row(cls, row: dict) -> "RecurringExpense":
        return cls(
            id=_parse_int(row.get("id")),
            tenant_id=_parse_int(row.get("tenant_id")),
            name=str(row.get("name") or ""),
            category=str(row.get("category") or "קבועות"),
            amount=_parse_float(row.get("amount")),
            frequency=str(row.get("frequency") or "monthly"),
            day_of_month=_parse_int(row.get("day_of_month"), default=1),
            active=_parse_bool(row.get("active")) if row.get("active") not in (None, "") else True,
            notes=_parse_optional_str(row.get("notes")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "category": self.category,
            "amount": self.amount,
            "frequency": self.frequency,
            "day_of_month": self.day_of_month,
            "active": "TRUE" if self.active else "FALSE",
            "notes": self.notes or "",
            "created_at": _dt_to_str(self.created_at),
        }


@dataclass
class RecurringIncome:
    id: int
    tenant_id: int
    source: str
    category: str = "הכנסה"
    amount: float = 0.0
    frequency: str = "monthly"
    day_of_month: int = 1
    probability: int = 100
    active: bool = True
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "recurring_incomes"
    HEADERS = (
        "id", "tenant_id", "source", "category", "amount", "frequency",
        "day_of_month", "probability", "active", "notes", "created_at",
    )

    @classmethod
    def from_row(cls, row: dict) -> "RecurringIncome":
        return cls(
            id=_parse_int(row.get("id")),
            tenant_id=_parse_int(row.get("tenant_id")),
            source=str(row.get("source") or ""),
            category=str(row.get("category") or "הכנסה"),
            amount=_parse_float(row.get("amount")),
            frequency=str(row.get("frequency") or "monthly"),
            day_of_month=_parse_int(row.get("day_of_month"), default=1),
            probability=_parse_int(row.get("probability"), default=100),
            active=_parse_bool(row.get("active")) if row.get("active") not in (None, "") else True,
            notes=_parse_optional_str(row.get("notes")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source": self.source,
            "category": self.category,
            "amount": self.amount,
            "frequency": self.frequency,
            "day_of_month": self.day_of_month,
            "probability": self.probability,
            "active": "TRUE" if self.active else "FALSE",
            "notes": self.notes or "",
            "created_at": _dt_to_str(self.created_at),
        }

    @property
    def expected_value(self) -> float:
        return self.amount * (self.probability / 100.0)


@dataclass
class CashEvent:
    id: int
    tenant_id: int
    date: date = field(default_factory=date.today)
    direction: str = "in"
    amount: float = 0.0
    description: str = ""
    source_type: str = "manual"
    source_id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)

    TABLE = "cash_events"
    HEADERS = (
        "id", "tenant_id", "date", "direction", "amount", "description",
        "source_type", "source_id", "created_at",
    )

    @classmethod
    def from_row(cls, row: dict) -> "CashEvent":
        return cls(
            id=_parse_int(row.get("id")),
            tenant_id=_parse_int(row.get("tenant_id")),
            date=_parse_date(row.get("date")),
            direction=str(row.get("direction") or "in"),
            amount=_parse_float(row.get("amount")),
            description=str(row.get("description") or ""),
            source_type=str(row.get("source_type") or "manual"),
            source_id=_parse_optional_int(row.get("source_id")),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "date": _date_to_str(self.date),
            "direction": self.direction,
            "amount": self.amount,
            "description": self.description,
            "source_type": self.source_type,
            "source_id": self.source_id if self.source_id is not None else "",
            "created_at": _dt_to_str(self.created_at),
        }


ALL_MODELS = (Tenant, Debt, ExpectedIncome, RecurringExpense, RecurringIncome, CashEvent)
SCHEMA: dict[str, tuple[str, ...]] = {m.TABLE: m.HEADERS for m in ALL_MODELS}
