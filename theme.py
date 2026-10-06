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


# --- palettes ---------------------------------------------------------------
# The header band is deliberately the same warm off-white in both themes: the
# logo PNG has an opaque white ground, so a dark band would frame it in a white
# box. Its text is therefore pinned dark too, independent of the theme.
HEADER_BG = "#fdfaf5"
HEADER_INK = "#0c1112"
HEADER_RULE = ORANGE

_LIGHT = {
    "INK": "#0c1112",
    "MUTED": "#6b7680",
    "ACCENT_TEXT": ORANGE_DARK,
    "STEP_FILL": "#fff3e2",
    "BORDER": "#d8dde2",
    "TABLE_HEAD": "#f2f4f6",
    "TABLE_LINE": "#e2e6ea",
    "DISABLED_BG": "#e9ecef",
    "ERROR": "#a4283a",
    "WARNING": "#a6571f",
    "OK": "#1f6b55",
    "BLUE": "#2f6fa8",
}

# Dark is not an inversion: the accent is lightened so it reads on a dark
# ground, and the state colours are re-picked rather than reused - #a4283a on
# near-black is the unreadable case this fixes.
_DARK = {
    "INK": "#e6ecf1",
    "MUTED": "#9aa7b2",
    "ACCENT_TEXT": "#ffb866",
    "STEP_FILL": "#3a2b16",
    "BORDER": "#39424c",
    "TABLE_HEAD": "#242b32",
    "TABLE_LINE": "#2f3740",
    "DISABLED_BG": "#2a3038",
    "ERROR": "#e8899a",
    "WARNING": "#e0a469",
    "OK": "#6cc4a8",
    "BLUE": "#7fb4e6",
}

# Bound at import to the light set, rebound by apply() once the QApplication
# exists and its palette can be inspected.
INK = _LIGHT["INK"]
MUTED = _LIGHT["MUTED"]
ACCENT_TEXT = _LIGHT["ACCENT_TEXT"]
ERROR = _LIGHT["ERROR"]
WARNING = _LIGHT["WARNING"]
OK = _LIGHT["OK"]
BLUE = _LIGHT["BLUE"]
IS_DARK = False


def is_dark(app):
    """True when the system theme is dark, judged from the window colour."""
    return app.palette().color(app.palette().Window).lightness() < 128


def apply(app):
    """Pick the palette for the current theme and install the stylesheet."""
    global INK, MUTED, ACCENT_TEXT, ERROR, WARNING, OK, BLUE, IS_DARK
    IS_DARK = is_dark(app)
    values = _DARK if IS_DARK else _LIGHT
    INK = values["INK"]
    MUTED = values["MUTED"]
    ACCENT_TEXT = values["ACCENT_TEXT"]
    ERROR = values["ERROR"]
    WARNING = values["WARNING"]
    OK = values["OK"]
    BLUE = values["BLUE"]
    app.setStyleSheet(stylesheet(values))
    return IS_DARK


def stylesheet(values):
    """Build the stylesheet for one palette.

    Every rule that sets a colour sets its background too, or takes both from
    the same set - the original mixed fixed light fills with palette() roles,
    so dark mode produced light-grey text on a light fill and dark text on a
    dark one.
    """
    v = values
    return f"""
QWidget#headerWidget {{
    background: {HEADER_BG};
    border-bottom: 2px solid {HEADER_RULE};
}}
QLabel#statusHeader {{
    color: {HEADER_INK};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#statusHeaderIdle {{
    color: #5d6a74;
    font-size: 13px;
}}
QLabel#sectionLabel {{
    color: {v["MUTED"]};
    font-weight: 600;
    padding-top: 6px;
    letter-spacing: 0.4px;
}}
QPushButton#stepButton {{
    text-align: left;
    padding: 6px 10px;
    border: 1px solid {v["BORDER"]};
    border-radius: 4px;
    background: palette(button);
    color: palette(button-text);
}}
/* Orange means "this is what to do next". A finished step keeps its border
   but drops the fill, so the eye lands on the actionable one. */
QPushButton#stepButton:enabled {{
    border-color: {ORANGE};
    background: {v["STEP_FILL"]};
    color: {v["INK"]};
}}
QPushButton#stepButton[done="true"]:enabled {{
    border-color: {v["BORDER"]};
    background: palette(button);
    color: {v["MUTED"]};
}}
QPushButton#stepButton:enabled:hover {{
    background: {ORANGE};
    color: #0c1112;
}}
QPushButton#stepButton:disabled {{
    color: {v["MUTED"]};
}}
QPushButton#primaryButton {{
    padding: 6px 16px;
    border: 1px solid {ORANGE_DARK};
    border-radius: 4px;
    background: {ORANGE};
    color: #0c1112;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {ORANGE_DARK};
    color: #ffffff;
}}
QPushButton#primaryButton:disabled {{
    background: {v["DISABLED_BG"]};
    border-color: {v["BORDER"]};
    color: {v["MUTED"]};
}}
QHeaderView::section {{
    background: {v["TABLE_HEAD"]};
    border: none;
    border-right: 1px solid {v["TABLE_LINE"]};
    border-bottom: 1px solid {v["BORDER"]};
    padding: 4px 6px;
    font-weight: 600;
    color: {v["INK"]};
}}
"""
