import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from tables import DataFrameTable


def cell(table, row, col):
    return table.proxy.data(table.proxy.index(row, col))


@pytest.fixture
def table():
    t = DataFrameTable()
    t.set_new_data(pd.DataFrame({"Name": ["Peter", "anna", "Eva"], "Betrag": [10.0, 9.5, 100.0]}))
    return t


def test_every_row_is_shown():
    t = DataFrameTable()
    t.set_new_data(pd.DataFrame({"x": range(500)}))
    assert t.proxy.rowCount() == 500                  # was cut off at 200


def test_numbers_sort_as_numbers(table):
    table.view.sortByColumn(1, Qt.AscendingOrder)
    assert [cell(table, r, 1) for r in range(3)] == ["9.5", "10", "100"]


def test_filter_searches_all_columns_case_insensitively(table):
    table.filter.setText("ANNA")
    assert table.proxy.rowCount() == 1 and cell(table, 0, 0) == "anna"
    assert "1 von 3" in table.count.text()


def test_energy_data_shows_its_timestamps():
    t = DataFrameTable()
    t.set_new_data(pd.DataFrame({("AT1", "Anna", "CONSUMPTION", "Gesamt"): [1.0]},
                                index=pd.DatetimeIndex(["2026-07-01 00:15"])))
    assert cell(t, 0, 0) == "01.07.2026 00:15"
    assert t.model.headers[1] == "AT1 Anna CONSUMPTION Gesamt"
