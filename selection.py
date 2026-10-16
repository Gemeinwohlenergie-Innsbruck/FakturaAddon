"""Deciding who is included in a SEPA export or a mail run.

Kept in its own module, free of Qt and docx imports, so it can be tested
without a display or an Office install. These are the code paths that decide
whose account gets debited and who receives an invoice, so they are the ones
that most need tests.
"""

import re

import pandas as pd


def select_invoice_positions(invoice_list, invoice_details, selected_mask):
    """Return the detail rows belonging to the ticked rows of ``invoice_list``.

    ``selected_mask`` holds one boolean per row of ``invoice_list``, in row
    order - the same order the checkboxes were built in.

    Returns ``(details_of_selected, selected_names)``.

    The bug this replaces filtered ``invoice_details`` against *all* names in
    ``invoice_list`` rather than the selected ones, so unticking somebody had
    no effect and they were still debited.
    """
    mask = list(selected_mask)
    if len(mask) != len(invoice_list):
        raise ValueError(
            f"selection mask has {len(mask)} entries but the invoice list has "
            f"{len(invoice_list)} rows"
        )
    selected_names = invoice_list.loc[mask, "Empfänger Name"]
    if "Nummer" in invoice_list.columns and "Nummer" in invoice_details.columns:
        # By document, not by person: someone with an invoice and a credit
        # note has two rows, and selecting by name brought in both documents
        # when only one was ticked.
        selected = set(document_ids(invoice_list.loc[mask]))
        details = invoice_details[document_ids(invoice_details).isin(selected)]
    else:
        details = invoice_details[invoice_details["Empfänger Name"].isin(selected_names)]
    return details, selected_names


def _document_key(value):
    """Document numbers as text: Excel hands back 1017 as 1017.0."""
    if _is_blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _is_blank(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return not str(value).strip()


def document_id(row):
    """What identifies one document of an invoice export.

    The invoice number, once there is one. A preview export ("Vorschau" in
    EEG Faktura, before "Abrechnung durchführen") has no numbers at all, and
    keying on the blank number made every document of a preview the same
    document. Within one run each member has at most one document per type,
    so period, type and member number identify it: "Vorschau 2026-3/R12".
    """
    number = _document_key(row.get("Nummer"))
    if number:
        return number
    period = re.sub(r"^Abr_[A-Z]+-", "", str(row.get("Abrechnung", "") or "").strip())
    kind = str(row.get("Dokumenttyp", "") or "?").strip()[:1].upper() or "?"
    member = _document_key(row.get("Empfänger Mitgliedsnummer"))
    # The name too: a real export had one member number on two people.
    name = " ".join(str(row.get("Empfänger Name", "") or "").split())
    return f"Vorschau {period}/{kind}{member} {name}".rstrip()


def document_ids(frame):
    """document_id for every row, as a Series aligned with ``frame``."""
    if frame is None or frame.empty:
        return pd.Series([], index=getattr(frame, "index", None), dtype=object)
    return pd.Series([document_id(row) for _, row in frame.iterrows()], index=frame.index, dtype=object)


def _name_key(first, last):
    """Normalise a (first, last) name pair for matching across the two exports.

    Blanks out NaN so two unnamed surnames compare equal, and strips the
    trailing whitespace the energy export is known to carry.
    """
    def clean(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()

    return (clean(first), clean(last))


def members_with_invoices(masterdata, invoice_details,
                          master_first="Name 1", master_last="Name 2",
                          invoice_first="Empfänger Vorame",
                          invoice_last="Empfänger Nachname"):
    """Rows of ``masterdata`` whose full name appears in ``invoice_details``.

    Matches on the (first, last) pair. Testing the two columns independently -
    ``first.isin(...) & last.isin(...)`` - also matched anybody who shared a
    first name with one invoice recipient and a surname with another, so
    members with no invoice were queued to receive somebody else's mail.
    """
    invoice_pairs = {}
    numbers = (invoice_details["Empfänger Mitgliedsnummer"]
               if "Empfänger Mitgliedsnummer" in invoice_details else [None] * len(invoice_details))
    for first, last, number in zip(invoice_details[invoice_first],
                                   invoice_details[invoice_last], numbers):
        invoice_pairs.setdefault(_name_key(first, last), set()).add(_document_key(number))
    has_numbers = "Mit. Nr." in masterdata.columns
    mask = []
    for _, row in masterdata.iterrows():
        pair = _name_key(row[master_first], row[master_last])
        wanted = invoice_pairs.get(pair)
        if wanted is None:
            mask.append(False)
        elif has_numbers and wanted - {""}:
            # Same name, other membership: only the one with an invoice.
            mask.append(_document_key(row["Mit. Nr."]) in wanted)
        else:
            mask.append(True)
    columns = [master_first, master_last, "E-Mail"] + (["Mit. Nr."] if has_numbers else [])
    return masterdata.loc[mask, columns].drop_duplicates()


def documents_of_member(invoice_list, first, last, member=None,
                        invoice_first="Empfänger Vorame", invoice_last="Empfänger Nachname"):
    """Document ids of the member with this name pair (and member number, if given)."""
    if "Nummer" not in invoice_list.columns:
        return []
    wanted = _name_key(first, last)
    member = _document_key(member)
    return [document_id(row) for _, row in invoice_list.iterrows()
            if _name_key(row[invoice_first], row[invoice_last]) == wanted
            and (not member or _document_key(row.get("Empfänger Mitgliedsnummer")) == member)]


def person_keys(frame, member_column="Empfänger Mitgliedsnummer", name_column="Empfänger Name"):
    """(member number, name) per row: who a document belongs to.

    The name alone is not enough: one person can hold two memberships, with
    two addresses and two accounts, and each has its own invoice. Grouping
    by name merged them into one PDF and one payment from one account.
    """
    members = (frame[member_column].map(_document_key) if member_column in frame
               else pd.Series([""] * len(frame), index=frame.index))
    names = frame[name_column].map(lambda n: " ".join(str(n).split()))
    return pd.Series(list(zip(members, names)), index=frame.index, dtype=object)


def invoice_file_stem(year, quarter, first, last, member=None):
    """"Rechnung_2026_q3_Anna_Müller" - shared by the invoice run and the mail run.

    Both used to build it themselves, and a member with no surname (a
    company, an association) came out as "..._nan": empty Excel cells are
    NaN. That only worked because both sides got it equally wrong. Blank
    parts are dropped, spaces trimmed, and characters a file name cannot
    hold (a "/" in a company name) replaced.
    """
    parts = [_document_key(part) for part in (first, last)]
    name = "_".join(" ".join(p.split()) for p in parts if p)
    name = re.sub(r'[\\/:*?"<>|]+', "-", name) or "ohne_Name"
    # The member number keeps two memberships of one person apart; without it
    # the second invoice overwrote the first.
    member = _document_key(member)
    return f"Rechnung_{year}_q{quarter}_{name}" + (f"_{member}" if member else "")
