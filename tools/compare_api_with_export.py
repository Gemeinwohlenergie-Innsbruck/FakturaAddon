"""Check the API import against an Energy Report export, cell by cell.

    .venv/bin/python tools/compare_api_with_export.py ENERGY_REPORT.xlsx STAMMDATEN.xlsx

Runs the app's own API import (eegfaktura_api.fetch_quarter) for the
export's quarter and community, and compares the result with the export as
the app loads it. Asks for the EEG Faktura password with getpass, never
echoes or stores it, and prints only counts, dates and community totals -
no member data. Read-only: one POST to /energystore/query/rawdata.

Download both files the same day you run this. Grid operators correct
allocations for weeks after a quarter ends, so an older export differs from
today's data in "Anteil" and "Eigendeckung" without anything being wrong.
"""
import getpass
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eegfaktura_api as api                                  # noqa: E402
from importing import load_masterdata_meta                   # noqa: E402

TOLERANCE = 1e-6        # the export rounds to 6 decimals


def read_export(path):
    energy = pd.read_excel(path, sheet_name="Energiedaten", skiprows=[7, 8, 9],
                           header=[1, 2, 3, 6], index_col=[0])
    energy.index = pd.to_datetime(energy.index, format="%d.%m.%Y %H:%M:%S")
    energy = energy.sort_index()
    try:
        qov = pd.read_excel(path, sheet_name="QoV Log", skiprows=[7, 8, 9],
                            header=[1, 2, 3, 6], index_col=[0])
        qov.index = pd.to_datetime(qov.index, format="%d.%m.%Y %H:%M:%S")
    except ValueError:
        qov = None          # newer exports mark quality by cell colour instead
    return energy, qov


def labels_by_column(qov):
    """Value column -> its QoV labels (the column right after it)."""
    if qov is None:
        return {}
    cols = list(qov.columns)
    return {c: qov.iloc[:, i + 1] for i, c in enumerate(cols)
            if c[0] != "QoV" and i + 1 < len(cols) and cols[i + 1][0] == "QoV"}


def main(export_path, members_path):
    export, export_qov = read_export(export_path)
    members = pd.read_excel(members_path, sheet_name="Mitglieder")
    tenant, ec_id = api.community_from_meta(load_masterdata_meta(members_path))
    first = export.index[0]
    year, quarter = first.year, (first.month - 1) // 3 + 1
    print(f"\nExport: {tenant} {year} Q{quarter}, {export.shape[1]} columns, {len(export)} rows")

    user = input("EEG Faktura username (email): ").strip()
    password = getpass.getpass("Password (not echoed): ")
    energy, qov, unmatched = api.fetch_quarter(user, password, tenant, ec_id,
                                               year, quarter, members)
    password = None

    problems = 0
    print(f"\nAPI:    {energy.shape[1]} columns, {len(energy)} rows, "
          f"{len(unmatched)} metering point(s) with readings but no member")
    problems += len(unmatched)

    only_api = set(energy.columns) - set(export.columns)
    only_export = set(export.columns) - set(energy.columns)
    print(f"Columns: {len(only_export)} only in the export, {len(only_api)} only from the API")
    problems += len(only_api) + len(only_export)

    same_index = energy.index.equals(export.index)
    print(f"Rows:    {'identical' if same_index else 'DIFFERENT'} "
          f"({export.index[0]} .. {export.index[-1]})")
    problems += not same_index

    common = [c for c in export.columns if c in set(energy.columns)]
    a = energy[common].reindex(export.index).astype(float)
    x = export[common].astype(float)
    blank_mismatch = int((a.isna() != x.isna()).sum().sum())
    print(f"Empty cells: {int(x.isna().sum().sum())} in the export, "
          f"{blank_mismatch} that only one side leaves empty")
    problems += blank_mismatch

    print("\nPer metercode: cells differing by more than rounding, and quarter totals")
    diff = (a - x).abs() > TOLERANCE
    for metercode in dict.fromkeys(c[-1] for c in common):
        cols = [c for c in common if c[-1] == metercode]
        cells = diff[cols]
        n = int(cells.sum().sum())
        meters = int(cells.any(axis=0).sum())
        line = f"  {n:6d} cells, {meters:2d} meters  {metercode}"
        if n:
            days = cells.any(axis=1)
            day_list = sorted(set(days[days].index.date))
            line += f"\n         on {len(day_list)} day(s), {day_list[0]} .. {day_list[-1]}"
        line += (f"\n         total {np.nansum(x[cols].to_numpy()):,.3f} kWh in the export, "
                 f"{np.nansum(a[cols].to_numpy()):,.3f} kWh from the API")
        print(line)
        problems += n

    labels = labels_by_column(export_qov)
    if labels:
        api_labels = {}
        q_cols = list(qov.columns)
        for i, c in enumerate(q_cols):
            if c[0] != "QoV" and i + 1 < len(q_cols):
                api_labels[c] = qov.iloc[:, i + 1]
        mismatched = l3_export = l3_api = 0
        for c, lab in labels.items():
            if c not in api_labels:
                continue
            ours = api_labels[c].reindex(lab.index)
            both = lab.notna() & ours.notna()
            mismatched += int((lab[both] != ours[both]).sum())
            l3_export += int((lab == "L3").sum())
            l3_api += int((api_labels[c] == "L3").sum())
        print(f"\nQuality labels: {mismatched} differ on the rows the QoV Log lists; "
              f"L3 cells: {l3_export} in the export, {l3_api} from the API")
        problems += mismatched
    else:
        print("\nQuality labels: the export has no QoV Log sheet to compare with")

    print("\nVERDICT:", "identical" if not problems else
          f"{problems} difference(s) - if the export is not from today, "
          "re-download it and compare again before trusting either")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(os.path.expanduser(sys.argv[1]), os.path.expanduser(sys.argv[2]))
