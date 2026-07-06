"""CSV export tests — header, ordering, missing keys, RFC-4180 escaping."""
import csv
import io

from app.services.analytics.export import journal_csv, ledger_csv, to_csv


def test_header_written_even_with_no_rows():
    out = ledger_csv([])
    assert out.strip() == ("timestamp_ms,bot,market,direction,stake,entry_price,exit_price,"
                           "cash_before,cash_after,fees,funding,status,realized_pnl,reason")


def test_ledger_row_maps_columns_in_order():
    row = {"ts_ms": 1000, "bot": "trend_breakout", "market": "BTCUSDT", "direction": "long",
           "stake": "3000.00", "entry_price": "60000", "exit_price": "61000",
           "cash_before": "100000.00", "cash_after": "100500.00", "fees": "5.5",
           "funding": "0.0", "status": "won", "realized_pnl": "500.00"}
    lines = ledger_csv([row]).strip().splitlines()
    assert len(lines) == 2
    parsed = list(csv.reader(io.StringIO(ledger_csv([row]))))
    assert parsed[1][0] == "1000" and parsed[1][1] == "trend_breakout"
    assert parsed[1][11] == "won" and parsed[1][12] == "500.00"


def test_missing_keys_render_empty():
    parsed = list(csv.reader(io.StringIO(ledger_csv([{"bot": "x"}]))))
    assert parsed[1][1] == "x"
    assert parsed[1][0] == "" and parsed[1][12] == ""


def test_csv_escaping_of_commas_quotes_newlines():
    row = {"reason": 'spread, then "spiked"\nthen recovered', "bot": "b"}
    out = ledger_csv([row])
    parsed = list(csv.reader(io.StringIO(out)))
    # The reason round-trips intact despite comma/quote/newline.
    assert parsed[1][-1] == 'spread, then "spiked"\nthen recovered'


def test_journal_csv_columns():
    row = {"closed_ts_ms": 5, "symbol": "ETHUSDT", "side": "sell", "pnl": "-20.00",
           "fees": "1.0", "funding": "0.0", "entry_reason": "mean reversion",
           "exit_reason": "stop_loss"}
    parsed = list(csv.reader(io.StringIO(journal_csv([row]))))
    assert parsed[0] == ["closed_ts_ms", "symbol", "side", "realized_pnl", "fees",
                         "funding", "entry_reason", "exit_reason"]
    assert parsed[1][3] == "-20.00" and parsed[1][7] == "stop_loss"


def test_none_row_values_empty():
    parsed = list(csv.reader(io.StringIO(to_csv([{"a": None}], [("a", "A")]))))
    assert parsed[1] == [""]
