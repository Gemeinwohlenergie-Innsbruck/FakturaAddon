import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporting import resolve_name_in_energydata


def energy_frame(*names):
    """A minimal stand-in for the four-level energy export columns."""
    columns = pd.MultiIndex.from_tuples(
        [("AT00512000000000000000003016030" + str(i), name, "CONSUMPTION",
          "Gesamtverbrauch lt. Messung (bei Teilnahme gem. Erzeugung) [KWH]")
         for i, name in enumerate(names)],
        names=["MeteringpointID", "Name", "Energy direction", "Quantity"])
    return pd.DataFrame([[1.0] * len(names)], columns=columns)


def test_exact_name_is_found():
    assert resolve_name_in_energydata(energy_frame("Anna Müller"), "Anna Müller") == "Anna Müller"


def test_trailing_space_in_energy_export_is_tolerated():
    """The energy export pads some names; Faktura does not."""
    assert resolve_name_in_energydata(energy_frame("Anna Müller "), "Anna Müller") == "Anna Müller "


def test_unknown_name_returns_none_rather_than_raising():
    """The caller now skips this member and reports it, instead of aborting
    the whole batch and hanging the progress dialog."""
    assert resolve_name_in_energydata(energy_frame("Peter Schmidt"), "Anna Müller") is None
