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
    invoice_pairs = {
        _name_key(first, last)
        for first, last in zip(invoice_details[invoice_first],
                               invoice_details[invoice_last])
    }
    mask = [
        _name_key(first, last) in invoice_pairs
        for first, last in zip(masterdata[master_first], masterdata[master_last])
    ]
    columns = [master_first, master_last, "E-Mail"]
    return masterdata.loc[mask, columns].drop_duplicates()


def documents_of_member(invoice_list, first, last,
                        invoice_first="Empfänger Vorame", invoice_last="Empfänger Nachname"):
    """Document numbers of the member with this (first, last) name pair."""
    if "Nummer" not in invoice_list.columns:
        return []
    wanted = _name_key(first, last)
    return [document_id(row) for _, row in invoice_list.iterrows()
            if _name_key(row[invoice_first], row[invoice_last]) == wanted]
