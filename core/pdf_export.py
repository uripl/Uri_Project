"""PDF export of the cash-flow report.

Streamlit's browser-print pipeline produces an unusably ugly layout, so this
module renders a self-contained A4 PDF using ReportLab. Hebrew text is
preprocessed with python-bidi to flip RTL runs into visual order — ReportLab
itself draws characters strictly left-to-right and has no bidi engine.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from datetime import date

import pandas as pd
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core import forecast, repository as repo
from core.formatting import fmt_currency, fmt_date

# Hebrew-capable fonts that ship with Debian/Ubuntu (Streamlit Cloud's base
# image) and common dev machines. First match wins; bold is optional.
_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ),
    ("/Library/Fonts/Arial Unicode.ttf", None),
    ("C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"),
]

_FONT_REGULAR = "Hebrew"
_FONT_BOLD = "Hebrew-Bold"


def _register_fonts() -> tuple[str, str]:
    if _FONT_REGULAR in pdfmetrics.getRegisteredFontNames():
        return _FONT_REGULAR, _FONT_BOLD
    for reg_path, bold_path in _FONT_CANDIDATES:
        if not os.path.exists(reg_path):
            continue
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, reg_path))
        if bold_path and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold_path))
        else:
            pdfmetrics.registerFont(TTFont(_FONT_BOLD, reg_path))
        return _FONT_REGULAR, _FONT_BOLD
    # No Hebrew-capable TTF found — fall back to Helvetica. Hebrew glyphs will
    # render as boxes, but at least the PDF generates.
    return "Helvetica", "Helvetica-Bold"


def _rtl(text) -> str:
    """Flip RTL runs in `text` into visual order for ReportLab.

    Numbers, Latin, and other LTR runs are kept in place — python-bidi
    implements the Unicode bidi algorithm and handles mixing correctly."""
    if text is None:
        return ""
    return get_display(str(text))


def _rtl_row(row: list) -> list:
    """RTL-prep every string cell in a row and reverse the column order so the
    first logical column appears on the right side of the visually rendered
    table."""
    return [_rtl(c) if isinstance(c, str) else c for c in reversed(row)]


@dataclass
class ReportSections:
    kpis: bool = True
    monthly: bool = True
    debt_matrix: bool = True
    events: bool = False
    events_limit: int = 30


def build_cashflow_report(
    tenant_id: int,
    sections: ReportSections,
    start_date: date | None = None,
    horizon_days: int = 180,
    client_name_override: str | None = None,
    note: str | None = None,
) -> bytes:
    """Render the cash-flow report as PDF bytes."""
    if start_date is None:
        start_date = date.today()

    font_reg, font_bold = _register_fonts()
    tenant = repo.get_tenant(tenant_id)
    display_name = (client_name_override or "").strip() or tenant.name

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"דוח תזרים - {tenant.name}",
        author="Cash Flow Dashboard",
    )

    base = ParagraphStyle(
        "base",
        fontName=font_reg,
        fontSize=10,
        leading=13,
        alignment=TA_RIGHT,
    )
    title = ParagraphStyle(
        "title",
        parent=base,
        fontName=font_bold,
        fontSize=20,
        leading=24,
        spaceAfter=4,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName=font_bold,
        fontSize=13,
        leading=16,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#0969da"),
    )
    caption = ParagraphStyle(
        "caption",
        parent=base,
        fontSize=9,
        textColor=colors.HexColor("#57606a"),
    )

    story: list = []
    story.append(Paragraph(_rtl(f"דוח תזרים מזומנים — {display_name}"), title))
    story.append(
        Paragraph(
            _rtl(f"נוצר בתאריך {fmt_date(date.today())} · טווח תחזית: {horizon_days} ימים מ-{fmt_date(start_date)}"),
            caption,
        )
    )
    if note:
        story.append(Spacer(1, 4))
        story.append(Paragraph(_rtl(note), base))

    if sections.kpis:
        _add_kpis(story, tenant_id, tenant, start_date, horizon_days, font_reg, font_bold, h2)

    if sections.monthly:
        _add_monthly_table(story, tenant_id, tenant, start_date, horizon_days, font_reg, font_bold, h2)

    if sections.debt_matrix:
        _add_debt_matrix(story, tenant_id, tenant, start_date, font_reg, font_bold, h2, caption)

    if sections.events:
        _add_events(story, tenant_id, tenant, sections.events_limit, font_reg, font_bold, h2)

    doc.build(story)
    return buf.getvalue()


def _table_style(font_reg: str, font_bold: str, n_cols: int) -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font_reg),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("FONTNAME", (0, 0), (-1, 0), font_bold),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#24292f")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
        ]
    )


def _add_kpis(story, tenant_id, tenant, start_date, horizon_days, font_reg, font_bold, h2):
    balance_now = repo.current_balance(tenant_id, as_of=start_date)
    total_debt = forecast.total_open_debt(tenant_id)
    overdue = forecast.overdue_debt(tenant_id, as_of=start_date)
    inc_30d = forecast.expected_income_30d(tenant_id, as_of=start_date)
    curve = forecast.cumulative_cash_curve(tenant_id, start_date=start_date, horizon_days=horizon_days)
    zero_date = forecast.zero_crossing_date(curve)

    rows = [
        ["מדד", "ערך"],
        ["יתרת מזומן נוכחית", fmt_currency(balance_now, tenant.currency)],
        ["סך חוב פתוח", fmt_currency(total_debt, tenant.currency)],
        ["חוב באיחור", fmt_currency(overdue, tenant.currency)],
        ["הכנסה צפויה (30 יום)", fmt_currency(inc_30d, tenant.currency)],
        [
            "תאריך חציית 0 (לפי תחזית)",
            fmt_date(zero_date) if zero_date else "לא צפוי בטווח",
        ],
    ]
    data = [_rtl_row(r) for r in rows]
    table = Table(data, colWidths=[60 * mm, 110 * mm])
    table.setStyle(_table_style(font_reg, font_bold, 2))

    story.append(Paragraph(_rtl("מדדים עיקריים"), h2))
    story.append(table)


def _add_monthly_table(story, tenant_id, tenant, start_date, horizon_days, font_reg, font_bold, h2):
    df = forecast.monthly_cash_breakdown(tenant_id, start_date=start_date, horizon_days=horizon_days)
    if df.empty:
        story.append(Paragraph(_rtl("פירוט חודשי"), h2))
        story.append(Paragraph(_rtl("אין נתונים בטווח שנבחר."), ParagraphStyle("p", fontName=font_reg, fontSize=10, alignment=TA_RIGHT)))
        return

    header = ["חודש", "הכנסות", "הוצאות", "החזר חובות", "נטו"]
    rows = [header]
    totals = {"incomes": 0.0, "expenses": 0.0, "debt_payments": 0.0, "net": 0.0}
    for _, r in df.iterrows():
        period = r["period"]
        label = period.strftime("%m/%Y") if isinstance(period, (date, pd.Timestamp)) else str(period)
        rows.append(
            [
                label,
                fmt_currency(r["incomes"], tenant.currency),
                fmt_currency(r["expenses"], tenant.currency),
                fmt_currency(r["debt_payments"], tenant.currency),
                fmt_currency(r["net"], tenant.currency),
            ]
        )
        for k in totals:
            totals[k] += float(r[k])
    rows.append(
        [
            "סה״כ",
            fmt_currency(totals["incomes"], tenant.currency),
            fmt_currency(totals["expenses"], tenant.currency),
            fmt_currency(totals["debt_payments"], tenant.currency),
            fmt_currency(totals["net"], tenant.currency),
        ]
    )

    data = [_rtl_row(r) for r in rows]
    col_widths = [25 * mm, 30 * mm, 30 * mm, 35 * mm, 30 * mm]
    table = Table(data, colWidths=list(reversed(col_widths)))
    style = _table_style(font_reg, font_bold, 5)
    style.add("FONTNAME", (0, -1), (-1, -1), font_bold)
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f3f6"))
    style.add("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#24292f"))
    table.setStyle(style)

    story.append(Paragraph(_rtl("פירוט חודשי"), h2))
    story.append(table)


def _month_spans(start: date, count: int) -> list[tuple[date, date, str]]:
    spans = []
    y, m = start.year, start.month
    for _ in range(count):
        ms = date(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        me = date(ny, nm, 1)
        spans.append((ms, me, f"{m:02d}/{y}"))
        y, m = ny, nm
    return spans


def _add_debt_matrix(story, tenant_id, tenant, start_date, font_reg, font_bold, h2, caption):
    open_debts = [
        d
        for d in repo.list_debts(tenant_id, only_open=True)
        if max(d.original_amount - d.paid_amount, 0.0) > 0
    ]
    story.append(Paragraph(_rtl("פריסת חובות לחודשים"), h2))

    if not open_debts:
        p = ParagraphStyle("p", fontName=font_reg, fontSize=10, alignment=TA_RIGHT)
        story.append(Paragraph(_rtl("אין חובות פתוחים."), p))
        return

    # 6 months in the report keeps the table within an A4 page width without
    # needing a sideways layout. The interactive page still defaults to 12.
    months = _month_spans(date(start_date.year, start_date.month, 1), 6)
    month_labels = [lbl for _, _, lbl in months]

    header = ["נושה", "יתרה פתוחה", *month_labels, "סה״כ"]
    rows = [header]
    col_totals = {lbl: 0.0 for lbl in month_labels}
    grand_total = 0.0
    for debt in open_debts:
        installments = repo.list_debt_installments(tenant_id, debt.id, only_pending=True)
        remaining = max(debt.original_amount - debt.paid_amount, 0.0)
        row = [debt.creditor, fmt_currency(remaining, tenant.currency)]
        debt_total = 0.0
        for ms, me, lbl in months:
            in_month = sum(i.amount for i in installments if ms <= i.due_date < me)
            row.append(fmt_currency(in_month, tenant.currency) if in_month else "-")
            col_totals[lbl] += in_month
            debt_total += in_month
        row.append(fmt_currency(debt_total, tenant.currency))
        grand_total += debt_total
        rows.append(row)

    totals_row = ["סה״כ", ""]
    for lbl in month_labels:
        totals_row.append(fmt_currency(col_totals[lbl], tenant.currency))
    totals_row.append(fmt_currency(grand_total, tenant.currency))
    rows.append(totals_row)

    data = [_rtl_row(r) for r in rows]
    # Equal-width month columns; nudge the creditor column wider.
    n_months = len(month_labels)
    creditor_w = 30 * mm
    balance_w = 22 * mm
    total_w = 22 * mm
    available = 180 * mm - creditor_w - balance_w - total_w
    month_w = available / n_months
    widths = [creditor_w, balance_w] + [month_w] * n_months + [total_w]
    table = Table(data, colWidths=list(reversed(widths)))
    style = _table_style(font_reg, font_bold, len(header))
    style.add("FONTNAME", (0, -1), (-1, -1), font_bold)
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f3f6"))
    style.add("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#24292f"))
    table.setStyle(style)

    story.append(KeepTogether([table]))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            _rtl("הסכומים בכל תא מבוססים על הסדרי תשלום שנקבעו במערכת. תאים ריקים = לא תוכנן תשלום באותו חודש."),
            caption,
        )
    )


def _add_events(story, tenant_id, tenant, limit, font_reg, font_bold, h2):
    events = repo.list_cash_events(tenant_id)
    story.append(Paragraph(_rtl(f"תנועות אחרונות (עד {limit})"), h2))

    if not events:
        p = ParagraphStyle("p", fontName=font_reg, fontSize=10, alignment=TA_RIGHT)
        story.append(Paragraph(_rtl("אין תנועות רשומות."), p))
        return

    events = sorted(events, key=lambda e: e.date, reverse=True)[:limit]
    header = ["תאריך", "כיוון", "סכום", "תיאור"]
    rows = [header]
    for e in events:
        direction = "כניסה" if e.direction == "in" else "יציאה"
        rows.append([fmt_date(e.date), direction, fmt_currency(e.amount, tenant.currency), e.description or "-"])

    data = [_rtl_row(r) for r in rows]
    col_widths = [25 * mm, 20 * mm, 30 * mm, 105 * mm]
    table = Table(data, colWidths=list(reversed(col_widths)), repeatRows=1)
    table.setStyle(_table_style(font_reg, font_bold, 4))
    story.append(table)
