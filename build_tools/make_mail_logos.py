"""Transparent mail logos from assets/gei_logo.png (black text on white).

mail_logo.png       dark text, with a thin white outline: stays readable when
                    a client such as Gmail inverts the mail's colours but not
                    its images. On white the outline does not show.
mail_logo_dark.png  light text, for clients that honour
                    prefers-color-scheme: dark (Apple Mail, iOS, Outlook).

Run again if gei_logo.png changes:  python build_tools/make_mail_logos.py
"""

from pathlib import Path

from PIL import Image, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ORANGE = (255, 159, 52)
INK = (12, 17, 18)
LIGHT_INK = (244, 241, 236)


def split_layers(source):
    """White background removed: (orange alpha, ink alpha) per pixel.

    Every pixel is white blended with either the orange or the ink, so the
    blend factor is the alpha. The two never touch in this logo.
    """
    rgb = source.convert("RGB")
    orange = Image.new("L", rgb.size, 0)
    ink = Image.new("L", rgb.size, 0)
    o, k = orange.load(), ink.load()
    for y in range(rgb.size[1]):
        for x in range(rgb.size[0]):
            r, g, b = rgb.getpixel((x, y))
            if r - b > 40:
                o[x, y] = max(0, min(255, round((255 - b) * 255 / (255 - ORANGE[2]))))
            else:
                k[x, y] = max(0, min(255, round((255 - (r + g + b) / 3) * 255 / (255 - sum(INK) / 3))))
    return orange, ink


def compose(size, layers):
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for colour, alpha in layers:
        layer = Image.new("RGBA", size, colour + (0,))
        layer.putalpha(alpha)
        out = Image.alpha_composite(out, layer)
    return out


def main():
    source = Image.open(ASSETS / "gei_logo.png")
    orange, ink = split_layers(source)
    halo = Image.merge("L", [ink]).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.6))
    compose(source.size, [((255, 255, 255), halo), (ORANGE, orange), (INK, ink)]).save(
        ASSETS / "mail_logo.png", optimize=True)
    compose(source.size, [(ORANGE, orange), (LIGHT_INK, ink)]).save(
        ASSETS / "mail_logo_dark.png", optimize=True)


if __name__ == "__main__":
    main()
