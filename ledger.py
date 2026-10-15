"""What this computer has already done with which documents.

An append-only file of JSON lines next to the settings. It exists to stop
the one mistake that costs members real money: exporting the same direct
debits twice. Nothing at the bank prevents a second upload of a file with
new dates, and the app has no other memory between runs.

Entries are scoped by the community's own IBAN, because document numbers
are only unique within one community.
"""

import datetime as dt
import getpass
import json
import os

import config

LEDGER_NAME = "ledger.jsonl"
SEPA = "sepa"
MAIL = "mail"
APPROVAL = "approval"


def ledger_path():
    return config.user_data_dir() / LEDGER_NAME


def current_user():
    try:
        return getpass.getuser()
    except Exception:
        return ""


def record(kind, creditor, period, documents, path=None, **details):
    """Append one entry. ``documents`` maps document number -> amount (or None)."""
    entry = {
        "kind": kind,
        "at": dt.datetime.now().isoformat(timespec="seconds"),
        "by": current_user(),
        "creditor": creditor,
        "period": period,
        "documents": {str(k): (None if v is None else float(v)) for k, v in documents.items()},
    }
    entry.update(details)
    target = path or ledger_path()
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def entries(path=None):
    """Every readable entry, oldest first. A damaged line is skipped, not fatal."""
    target = path or ledger_path()
    if not os.path.exists(target):
        return []
    found = []
    with open(target, encoding="utf-8") as handle:
        for line in handle:
            try:
                found.append(json.loads(line))
            except ValueError:
                continue
    return found


def last_done(kind, creditor, path=None):
    """Document number -> 'dd.mm.yyyy HH:MM' of the latest entry of this kind."""
    done = {}
    for entry in entries(path):
        if entry.get("kind") != kind or entry.get("creditor") != creditor:
            continue
        try:
            when = dt.datetime.fromisoformat(entry["at"]).strftime("%d.%m.%Y %H:%M")
        except (KeyError, ValueError):
            when = "?"
        for number in entry.get("documents", {}):
            done[str(number)] = when
    return done
