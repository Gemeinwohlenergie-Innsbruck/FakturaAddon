"""Check the API's value slots against an Energy Report export of the same quarter.

    .venv/bin/python tools/compare_api_with_export.py ~/Downloads/CC100438-Energy-Report-20260401_20260630.xlsx

Asks for the EEG Faktura login (password via getpass, never echoed or
stored), fetches the export's period from the API, and for every metercode
reports which API slot reproduces it. Prints numbers only, no member data.
Read-only: one POST to /energystore/query/rawdata.
"""
import getpass
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eegfaktura_api as api   # noqa: E402


def main(path):
    excel = pd.read_excel(path, sheet_name="Energiedaten", skiprows=[7, 8, 9],
                          header=[1, 2, 3, 6], index_col=[0])
    excel.index = pd.to_datetime(excel.index, format="%d.%m.%Y %H:%M:%S")
    excel = excel.sort_index()
    first = excel.index[0]
    year, quarter = first.year, (first.month - 1) // 3 + 1
    tenant = os.path.basename(path).split("-")[0]
    print(f"Export: {tenant} {year} Q{quarter}, {excel.shape[1]} columns, {len(excel)} rows\n")

    user = input("EEG Faktura username (email): ").strip()
    password = getpass.getpass("Password (not echoed): ")
    ec_id = input("ecId (Gemeinschafts-ID from the member list): ").strip()
    start, end = api.quarter_range(year, quarter)
    raw = api.fetch_rawdata(user, password, tenant, ec_id, start, end)
    password = None

    qov_shapes = Counter()
    # metercode -> slot -> list of max abs differences, one per meter
    diffs = {}
    compared = 0
    for meter, entry in raw.items():
        samples = entry.get("data") or []
        if not samples or meter not in excel.columns.get_level_values(0):
            continue
        q = samples[0].get("qov")
        qov_shapes[f"{type(q).__name__}" + (f"[{len(q)}] e.g. {q}" if isinstance(q, list) else f" e.g. {q!r}")] += 1
        index = (pd.to_datetime([s["ts"] for s in samples], unit="ms", utc=True)
                 .tz_convert(api.TIMEZONE))
        keep = (index >= start) & (index < end)
        values = np.array([[np.nan if v is None else v for v in (s.get("value") or [])] + [np.nan] * 3
                           for s in samples], dtype=float)[keep, :3]
        local = index[keep].tz_localize(None)
        sub = excel.xs(meter, level=0, axis=1)
        compared += 1
        for col in sub.columns:
            metercode = col[-1]
            target = sub[col].reindex(local).to_numpy(dtype=float)
            for slot in range(3):
                d = np.nanmax(np.abs(values[:, slot] - target)) if np.isfinite(values[:, slot]).any() else np.inf
                diffs.setdefault(metercode, {}).setdefault(slot, []).append(d)

    print(f"\nMeters compared: {compared}")
    print("qov shapes:", dict(qov_shapes))
    print("\nmetercode -> worst difference per API slot (0 = identical)")
    for metercode, slots in diffs.items():
        worst = {slot: max(v) for slot, v in slots.items()}
        best = min(worst, key=worst.get)
        print(f"  slot {best}  {metercode}")
        print("          " + ", ".join(f"slot {s}: {w:.4g}" for s, w in sorted(worst.items())))
    print("\nThe app assumes:")
    for direction, codes in api.METERCODES.items():
        for slot, code in codes:
            print(f"  slot {slot}  {direction:<11}  {code}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(os.path.expanduser(sys.argv[1]))
