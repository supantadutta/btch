"""CSV export for reporting. RFC 4180 via the stdlib csv module (correct quoting
of commas/quotes/newlines). Pure functions — the API layer wraps the string in a
text/csv response."""
from __future__ import annotations

import csv
import io
from typing import Dict, List, Sequence

# Column order + header labels for each export (stable, human-readable).
LEDGER_COLUMNS: List[tuple[str, str]] = [
    ("ts_ms", "timestamp_ms"), ("bot", "bot"), ("market", "market"),
    ("direction", "direction"), ("stake", "stake"), ("entry_price", "entry_price"),
    ("exit_price", "exit_price"), ("cash_before", "cash_before"),
    ("cash_after", "cash_after"), ("fees", "fees"), ("funding", "funding"),
    ("status", "status"), ("realized_pnl", "realized_pnl"), ("reason", "reason"),
]

JOURNAL_COLUMNS: List[tuple[str, str]] = [
    ("closed_ts_ms", "closed_ts_ms"), ("symbol", "symbol"), ("side", "side"),
    ("pnl", "realized_pnl"), ("fees", "fees"), ("funding", "funding"),
    ("entry_reason", "entry_reason"), ("exit_reason", "exit_reason"),
]


def to_csv(rows: Sequence[Dict], columns: Sequence[tuple[str, str]]) -> str:
    """Serialize rows to CSV. `columns` is (source_key, header_label) pairs;
    missing keys render as empty. Always writes a header, even for zero rows."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_cell(row.get(key)) for key, _ in columns])
    return buf.getvalue()


def _cell(v) -> str:
    if v is None:
        return ""
    return str(v)


def ledger_csv(rows: Sequence[Dict]) -> str:
    return to_csv(rows, LEDGER_COLUMNS)


def journal_csv(rows: Sequence[Dict]) -> str:
    return to_csv(rows, JOURNAL_COLUMNS)
