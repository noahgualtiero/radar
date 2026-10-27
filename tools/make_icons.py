"""Erzeugt die PNG-Icons aus den Formen von static/logo.svg (nur nötig, wenn sich das Logo ändert).

    pip install Pillow && python tools/make_icons.py

Schreibt nach static/: apple-touch-icon.png (180, iOS rundet selbst ab), icon-192.png,
icon-512.png, favicon-32.png und og.png (1200×630 für Link-Vorschauen).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "static"
TOP, BOTTOM = (10, 132, 255), (94, 92, 230)  # #0A84FF → #5E5CE6
SS = 4  # Supersampling für glatte Kanten


def gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
    return img


def radar(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, rings: list[tuple[float, int]], width: float) -> None:
    """Ringe, Strahl mit Fächer, Ziel-Punkt und Mittelpunkt – wie im SVG-Logo."""
    for factor, alpha in rings:
        rr = r * factor
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(255, 255, 255, alpha), width=round(width))
    end = (cx + r * math.sin(math.radians(60)), cy - r * math.cos(math.radians(60)))
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=-90, end=-30, fill=(255, 255, 255, 60))
    draw.line([(cx, cy), end], fill=(255, 255, 255, 255), width=round(width * 1.2))
    blip = (cx + r * .75 * math.sin(math.radians(40)), cy - r * .75 * math.cos(math.radians(40)))
    for (x, y), rad in ((blip, width * 1.2), ((cx, cy), width * 1.4)):
        draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(255, 255, 255, 255))


def icon(size: int) -> Image.Image:
    s = size * SS
    base = gradient(s, s).convert("RGBA")
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    radar(ImageDraw.Draw(layer), s / 2, s / 2, s * 20 / 64, [(1, 80), (11 / 20, 130)], s * 2.5 / 64)
    return Image.alpha_composite(base, layer).resize((size, size), Image.LANCZOS)


def font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    for path, index in (("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0),
                        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0)):
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    return ImageFont.load_default()


def og() -> Image.Image:
    w, h = 1200 * 2, 630 * 2  # doppelte Auflösung, dann verkleinern
    base = gradient(w, h).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    radar(draw, w * .72, h / 2, h * .4, [(1, 50), (.66, 75), (.32, 105)], 12)
    draw.text((180, 470), "Radar", font=font(260, True), fill="white")
    draw.text((188, 780), "Newsradar für Paid Search", font=font(80, False), fill=(255, 255, 255, 220))
    return Image.alpha_composite(base, layer).resize((1200, 630), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    icon(180).convert("RGB").save(OUT / "apple-touch-icon.png")
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(32).save(OUT / "favicon-32.png")
    og().save(OUT / "og.png", optimize=True)
    print("Icons geschrieben nach", OUT)
