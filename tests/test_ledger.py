import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger


def test_exports_are_remembered_per_community(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.record(ledger.SEPA, "AT61", "Abr_YQ-2026-3", {"1001": 12.5, "1002": 3}, path=path)
    ledger.record(ledger.SEPA, "AT48", "Abr_YQ-2026-3", {"1001": 7}, path=path)
    assert set(ledger.last_done(ledger.SEPA, "AT61", path=path)) == {"1001", "1002"}
    assert set(ledger.last_done(ledger.SEPA, "AT48", path=path)) == {"1001"}
    assert ledger.last_done(ledger.MAIL, "AT61", path=path) == {}


def test_a_damaged_line_does_not_lose_the_rest(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.record(ledger.SEPA, "AT61", "p", {"1001": 1}, path=path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"kind": "sepa", "trunc\n')
    ledger.record(ledger.SEPA, "AT61", "p", {"1002": 1}, path=path)
    assert set(ledger.last_done(ledger.SEPA, "AT61", path=path)) == {"1001", "1002"}


def test_no_ledger_yet_means_nothing_done(tmp_path):
    assert ledger.last_done(ledger.SEPA, "AT61", path=tmp_path / "missing.jsonl") == {}
