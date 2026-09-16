"""Selecting which invoice positions go into a SEPA export.

Kept in its own module, free of Qt and docx imports, so it can be tested
without a display or an Office install. This is the code path that decides
whose account gets debited, so it is the one place that most needs a test.
"""


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
