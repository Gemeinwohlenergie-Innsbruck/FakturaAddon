"""Deciding who is included in a SEPA export or a mail run.

Kept in its own module, free of Qt and docx imports, so it can be tested
without a display or an Office install. These are the code paths that decide
whose account gets debited and who receives an invoice, so they are the ones
that most need tests.
"""

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
    details = invoice_details[invoice_details["Empfänger Name"].isin(selected_names)]
    return details, selected_names


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
