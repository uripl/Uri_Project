"""Storage abstraction: a `Store` interface backed by either Google Sheets or in-memory dicts.

The Store works with simple `dict` rows of primitives (str/int/float). Models in
`core.models` handle conversion to/from typed values via `to_row()` / `from_row()`.
"""
from __future__ import annotations

from typing import Iterable, Protocol

from core.models import SCHEMA


class Store(Protocol):
    def list_rows(self, table: str) -> list[dict]: ...
    def get_row(self, table: str, row_id: int) -> dict | None: ...
    def insert(self, table: str, fields: dict) -> dict: ...
    def update(self, table: str, row_id: int, fields: dict) -> None: ...
    def delete(self, table: str, row_id: int) -> None: ...
    def delete_where(self, table: str, predicate_fields: dict) -> int: ...


class MemoryStore:
    """In-process store. Used for tests and as a fallback when no credentials exist."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict]] = {t: [] for t in SCHEMA}
        self._counters: dict[str, int] = {t: 0 for t in SCHEMA}

    def list_rows(self, table: str) -> list[dict]:
        return [dict(r) for r in self._tables[table]]

    def get_row(self, table: str, row_id: int) -> dict | None:
        for r in self._tables[table]:
            if int(r.get("id", 0)) == int(row_id):
                return dict(r)
        return None

    def insert(self, table: str, fields: dict) -> dict:
        self._counters[table] += 1
        row = {**fields, "id": self._counters[table]}
        self._tables[table].append(row)
        return dict(row)

    def update(self, table: str, row_id: int, fields: dict) -> None:
        for r in self._tables[table]:
            if int(r.get("id", 0)) == int(row_id):
                for k, v in fields.items():
                    if k == "id":
                        continue
                    r[k] = v
                return
        raise KeyError(f"No row with id={row_id} in {table}")

    def delete(self, table: str, row_id: int) -> None:
        self._tables[table] = [
            r for r in self._tables[table] if int(r.get("id", 0)) != int(row_id)
        ]

    def delete_where(self, table: str, predicate_fields: dict) -> int:
        keep: list[dict] = []
        removed = 0
        for r in self._tables[table]:
            if all(str(r.get(k, "")) == str(v) for k, v in predicate_fields.items()):
                removed += 1
            else:
                keep.append(r)
        self._tables[table] = keep
        return removed


class SheetsStore:
    """Google Sheets-backed store using gspread.

    A single Google Sheets workbook holds one worksheet (tab) per table.
    Row 1 is a frozen header row; data starts on row 2. The `id` column is
    always column A.
    """

    def __init__(self, spreadsheet) -> None:
        self._ss = spreadsheet
        self._ws_cache: dict[str, object] = {}

    # ------------------------------------------------------------------ schema

    def ensure_schema(self) -> None:
        existing = {ws.title: ws for ws in self._ss.worksheets()}
        for table, headers in SCHEMA.items():
            headers_list = list(headers)
            if table not in existing:
                ws = self._ss.add_worksheet(title=table, rows=200, cols=max(len(headers_list), 5))
                ws.update(values=[headers_list], range_name="A1", value_input_option="RAW")
                try:
                    ws.freeze(rows=1)
                except Exception:
                    pass
            else:
                ws = existing[table]
                current = ws.row_values(1)
                if current != headers_list:
                    ws.update(values=[headers_list], range_name="A1", value_input_option="RAW")
                    try:
                        ws.freeze(rows=1)
                    except Exception:
                        pass

        # Remove the default "Sheet1" tab if present and at least one of our tabs exists.
        leftover = existing.get("Sheet1")
        if leftover is not None and any(t in existing or t in {ws.title for ws in self._ss.worksheets()} for t in SCHEMA):
            try:
                self._ss.del_worksheet(leftover)
            except Exception:
                pass

    # --------------------------------------------------------------- internals

    def _ws(self, table: str):
        if table not in self._ws_cache:
            self._ws_cache[table] = self._ss.worksheet(table)
        return self._ws_cache[table]

    def _read_table(self, table: str) -> tuple[list[str], list[list[str]]]:
        ws = self._ws(table)
        all_values = ws.get_all_values()
        if not all_values:
            return list(SCHEMA[table]), []
        headers = all_values[0]
        rows = all_values[1:]
        return headers, rows

    @staticmethod
    def _row_to_dict(headers: list[str], row_values: list) -> dict:
        out: dict = {}
        for i, h in enumerate(headers):
            out[h] = row_values[i] if i < len(row_values) else ""
        return out

    def _find_row_index(self, table: str, row_id: int) -> int | None:
        """Return 1-indexed sheet row number for the given id, or None."""
        ws = self._ws(table)
        ids = ws.col_values(1)
        for idx, v in enumerate(ids[1:], start=2):
            try:
                if int(float(v)) == int(row_id):
                    return idx
            except (TypeError, ValueError):
                continue
        return None

    # ------------------------------------------------------------------- API

    def list_rows(self, table: str) -> list[dict]:
        headers, rows = self._read_table(table)
        return [self._row_to_dict(headers, r) for r in rows if any(c != "" for c in r)]

    def get_row(self, table: str, row_id: int) -> dict | None:
        for r in self.list_rows(table):
            try:
                if int(float(r.get("id", 0))) == int(row_id):
                    return r
            except (TypeError, ValueError):
                continue
        return None

    def insert(self, table: str, fields: dict) -> dict:
        ws = self._ws(table)
        headers = list(SCHEMA[table])
        existing_rows = self.list_rows(table)
        next_id = 1
        for r in existing_rows:
            try:
                next_id = max(next_id, int(float(r.get("id", 0))) + 1)
            except (TypeError, ValueError):
                continue
        full_row = {**fields, "id": next_id}
        values = [_serialize_cell(full_row.get(h, "")) for h in headers]
        ws.append_row(values, value_input_option="RAW")
        return full_row

    def update(self, table: str, row_id: int, fields: dict) -> None:
        idx = self._find_row_index(table, row_id)
        if idx is None:
            raise KeyError(f"No row with id={row_id} in {table}")
        ws = self._ws(table)
        headers = list(SCHEMA[table])
        # Batch all cell updates for this row into a single API call (RAW mode
        # so dates/datetimes round-trip as the literal strings we wrote).
        import gspread.utils as _gsu
        batch = []
        for key, val in fields.items():
            if key == "id" or key not in headers:
                continue
            col = headers.index(key) + 1
            a1 = _gsu.rowcol_to_a1(idx, col)
            batch.append({"range": a1, "values": [[_serialize_cell(val)]]})
        if batch:
            ws.batch_update(batch, value_input_option="RAW")

    def delete(self, table: str, row_id: int) -> None:
        idx = self._find_row_index(table, row_id)
        if idx is None:
            return
        self._ws(table).delete_rows(idx)

    def delete_where(self, table: str, predicate_fields: dict) -> int:
        ws = self._ws(table)
        headers, rows = self._read_table(table)
        # Find row indices to delete (1-indexed sheet rows, descending so deletion stays correct).
        targets: list[int] = []
        for i, r in enumerate(rows, start=2):
            d = self._row_to_dict(headers, r)
            if all(str(d.get(k, "")) == str(v) for k, v in predicate_fields.items()):
                targets.append(i)
        for idx in sorted(targets, reverse=True):
            ws.delete_rows(idx)
        return len(targets)


def _serialize_cell(value) -> object:
    """Convert a Python value into something gspread can write."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value
