# PyInstaller spec for the macOS app bundle.
# Build with:  pyinstaller build_tools/FakturaAddon.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "assets"), "assets"),
    ],
    # docx2pdf reaches Word through appscript, which PyInstaller cannot see
    # by following imports alone.
    hiddenimports=["appscript", "docx2pdf"],
    excludes=["tkinter", "PyQt5.QtWebEngineWidgets", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="FakturaAddon", console=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FakturaAddon")

app = BUNDLE(
    coll,
    name="FakturaAddon.app",
    icon=str(ROOT / "build_tools" / "AppIcon.icns"),
    bundle_identifier="at.gemeinwohlenergie.fakturaaddon",
    info_plist={
        "CFBundleName": "FakturaAddon",
        "CFBundleDisplayName": "Faktura Infinity Addon",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHumanReadableCopyright": "Gemeinwohl Energie Innsbruck",
        # Retina: without this Qt renders into a 1x buffer and the whole UI
        # looks soft on any modern Mac.
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
