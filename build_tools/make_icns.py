"""Generate build_tools/AppIcon.icns from assets/app_icon.png.

Kept as a script rather than a committed binary: the .icns is build output,
and iconutil is only available on macOS anyway.
"""
import pathlib
import shutil
import subprocess

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE.parent / "assets" / "app_icon.png"
ICONSET = HERE / "AppIcon.iconset"
ICNS = HERE / "AppIcon.icns"


def main():
    source = Image.open(SOURCE)
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True)
    for size in (16, 32, 128, 256, 512):
        source.resize((size, size), Image.LANCZOS).save(ICONSET / f"icon_{size}x{size}.png")
        source.resize((size * 2, size * 2), Image.LANCZOS).save(
            ICONSET / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)], check=True)
    print(f"wrote {ICNS}")


if __name__ == "__main__":
    main()
