"""Colours and the application stylesheet.

The palette is not invented: ORANGE and INK are sampled from the GEI logo
inside the invoice template, and BLUE is the colour the invoice charts already
use for grid energy (with ORANGE as community energy). So the app, the
invoices and the logo agree.

Accent colours are used for emphasis and state, not decoration. Everything
else stays on the system palette so the app still looks native.
"""

import os
import sys

# --- brand -----------------------------------------------------------------
ORANGE = "#ff9f34"        # the logo's sun, and community energy in the charts
ORANGE_DARK = "#c2711a"   # ORANGE is too light for text on white
ORANGE_TINT = "#fff3e2"
INK = "#0c1112"           # the logo's wordmark
BLUE = "#69a4dc"          # grid energy in the charts

# --- state -----------------------------------------------------------------
ERROR = "#a4283a"
WARNING = "#a6571f"
OK = "#1f6b55"
MUTED = "#6b7680"

HEADER_BG = "#fdfaf5"     # warm off-white, so the logo sits on its own ground
HEADER_RULE = ORANGE


def resource_path(*parts):
    """Locate a bundled file, in a checkout and inside a PyInstaller build.

    A frozen app unpacks --add-data under sys._MEIPASS, not next to the exe.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def logo_path():
    return resource_path("assets", "gei_logo.png")


# Deliberately narrow: the header band, the step list, section labels and the
# primary buttons. Tables, menus and dialogs keep the system look.
STYLESHEET = f"""
QLabel#headerBand {{
    background: {HEADER_BG};
}}
QWidget#headerWidget {{
    background: {HEADER_BG};
    border-bottom: 2px solid {HEADER_RULE};
}}
QLabel#statusHeader {{
    color: {INK};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#statusHeaderIdle {{
    color: {MUTED};
    font-size: 13px;
}}
QLabel#sectionLabel {{
    color: {MUTED};
    font-weight: 600;
    padding-top: 6px;
    letter-spacing: 0.4px;
}}
QPushButton#stepButton {{
    text-align: left;
    padding: 6px 10px;
    border: 1px solid #d8dde2;
    border-radius: 4px;
    background: palette(button);
}}
/* Orange means "this is what to do next". A finished step keeps its border
   but drops the fill, so the eye lands on the actionable one. */
QPushButton#stepButton:enabled {{
    border-color: {ORANGE};
    background: {ORANGE_TINT};
    color: {INK};
}}
QPushButton#stepButton[done="true"]:enabled {{
    border-color: #d8dde2;
    background: palette(button);
    color: {MUTED};
}}
QPushButton#stepButton:enabled:hover {{
    background: {ORANGE};
    color: {INK};
}}
QPushButton#stepButton:disabled {{
    color: {MUTED};
}}
QPushButton#primaryButton {{
    padding: 6px 16px;
    border: 1px solid {ORANGE_DARK};
    border-radius: 4px;
    background: {ORANGE};
    color: {INK};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {ORANGE_DARK};
    color: white;
}}
QPushButton#primaryButton:disabled {{
    background: #e9ecef;
    border-color: #d8dde2;
    color: {MUTED};
}}
QHeaderView::section {{
    background: #f2f4f6;
    border: none;
    border-right: 1px solid #e2e6ea;
    border-bottom: 1px solid #d8dde2;
    padding: 4px 6px;
    font-weight: 600;
    color: {INK};
}}
"""
