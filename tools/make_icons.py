"""Erzeugt die PNG-Icons aus den Formen von static/logo.svg (nur nötig, wenn sich das Logo ändert).

    pip install Pillow && python tools/make_icons.py

Schreibt nach static/: apple-touch-icon.png (180, iOS rundet selbst ab), icon-192.png,
icon-512.png, favicon-32.png, favicon-16.png (vereinfacht) und og.png (1200×630 für Link-Vorschauen).
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


def small_icon(size: int, rounded: bool = True) -> Image.Image:
    """Kräftiges Logo wie static/favicon.svg: ein Ring, dicker Strahl, grosse Punkte. Gilt für Favicon und
    App-Icons; rounded=False für iOS und Manifest (das System rundet selbst ab)."""
    s = size * SS
    base = gradient(s, s).convert("RGBA")
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    u = s / 64
    cx = cy = 32 * u
    draw.ellipse([cx - 20 * u, cy - 20 * u, cx + 20 * u, cy + 20 * u], outline=(255, 255, 255, 153), width=round(5 * u))
    draw.line([(cx, cy), (49.32 * u, 22 * u)], fill=(255, 255, 255, 255), width=round(6.5 * u))
    for x, y, r in ((49.32, 22, 3.25), (32, 32, 6), (41, 45, 5)):
        draw.ellipse([(x - r) * u, (y - r) * u, (x + r) * u, (y + r) * u], fill=(255, 255, 255, 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=round(14.5 * u), fill=255)
    out = Image.alpha_composite(base, layer)
    if rounded:
        out.putalpha(mask)
    return out.resize((size, size), Image.LANCZOS)


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
    small_icon(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    small_icon(192, rounded=False).save(OUT / "icon-192.png")
    small_icon(512, rounded=False).save(OUT / "icon-512.png")
    small_icon(32).save(OUT / "favicon-32.png")
    small_icon(16).save(OUT / "favicon-16.png")
    og().save(OUT / "og.png", optimize=True)
    print("Icons geschrieben nach", OUT)
