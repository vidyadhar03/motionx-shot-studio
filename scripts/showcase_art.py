"""Procedural sample art for the showcase workspace: neutral, fictional, generated from code (no third-party images,
nothing from any real project). Every image carries a small "SAMPLE ART" tag so it can't pass for model output."""
from __future__ import annotations

import math
import random
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def gradient(w: int, h: int, top, bottom) -> Image.Image:
    mask = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), mask)


def glow(img: Image.Image, cx: float, cy: float, r: float, color, strength: float = 1.0) -> None:
    g = Image.radial_gradient("L").point(lambda v: min(255, int(v * 1.4143))).resize((int(r * 2), int(r * 2)))
    mask = ImageChops.invert(g).point(lambda v: int(v * v / 255 * strength))
    layer = Image.new("RGB", mask.size, color)
    img.paste(layer, (int(cx - r), int(cy - r)), mask)


def grain(img: Image.Image, amount: float = 0.05, seed: int = 1) -> Image.Image:
    noise = Image.effect_noise(img.size, 28).convert("RGB")
    return Image.blend(img, noise, amount)


def vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    g = Image.radial_gradient("L").resize(img.size).point(lambda v: int(v * strength))
    return Image.composite(Image.new("RGB", img.size, (4, 6, 12)), img, g)


def tag(img: Image.Image, text: str = "SAMPLE ART") -> Image.Image:
    d = ImageDraw.Draw(img, "RGBA")
    f = _font(max(12, img.width // 110))
    tw = d.textlength(text, font=f)
    x, y = img.width - tw - img.width // 60, img.height - img.height // 22
    d.text((x, y), text, fill=(255, 255, 255, 120), font=f)
    return img


def stars(img: Image.Image, n: int, horizon: float, seed: int) -> None:
    rnd, d = random.Random(seed), ImageDraw.Draw(img, "RGBA")
    for _ in range(n):
        x, y = rnd.random() * img.width, rnd.random() * img.height * horizon
        a = rnd.randint(70, 220)
        s = rnd.choice((1, 1, 1, 2))
        d.ellipse([x, y, x + s, y + s], fill=(255, 245, 225, a))


def sea(img: Image.Image, horizon: int, top, bottom, seed: int, shimmer=(255, 190, 110)) -> None:
    w, h = img.size
    img.paste(gradient(w, h - horizon, top, bottom), (0, horizon))
    rnd, d = random.Random(seed), ImageDraw.Draw(img, "RGBA")
    for _ in range(260):
        y = horizon + (rnd.random() ** 1.6) * (h - horizon)
        x = rnd.random() * w
        L = 20 + (y - horizon) * 0.35 * rnd.random() * 3
        d.line([x, y, x + L, y], fill=(*shimmer, rnd.randint(18, 70)), width=1 + int((y - horizon) / 140))


def lighthouse(img: Image.Image, x: float, base: float, height: float, lit: bool = True, col=(18, 22, 34)) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w0, w1 = height * 0.16, height * 0.10
    d.polygon([(x - w0, base), (x + w0, base), (x + w1, base - height), (x - w1, base - height)], fill=col)
    for i in range(1, 4):                                        # bands
        yy = base - height * i / 4
        ww = w0 + (w1 - w0) * i / 4
        d.line([(x - ww, yy), (x + ww, yy)], fill=(40, 46, 66, 255), width=max(2, int(height / 90)))
    gal = base - height
    d.rectangle([x - w1 * 1.5, gal, x + w1 * 1.5, gal + height * 0.025], fill=col)
    d.rectangle([x - w1 * 0.8, gal - height * 0.09, x + w1 * 0.8, gal], fill=(255, 205, 120, 255) if lit else col)
    d.polygon([(x - w1, gal - height * 0.09), (x + w1, gal - height * 0.09), (x, gal - height * 0.17)], fill=col)
    if lit:
        glow(img, x, gal - height * 0.045, height * 0.55, (255, 190, 100), 0.9)


def boat(d: ImageDraw.ImageDraw, x: float, y: float, s: float, col=(10, 12, 20)) -> None:
    d.polygon([(x - s, y), (x + s, y), (x + s * 0.7, y + s * 0.28), (x - s * 0.8, y + s * 0.28)], fill=col)
    d.line([(x, y), (x, y - s * 1.5)], fill=col, width=max(2, int(s / 14)))
    d.polygon([(x + 3, y - s * 1.4), (x + 3, y - s * 0.2), (x + s * 0.7, y - s * 0.2)], fill=col)


def figure(img: Image.Image, cx: float, base: float, h: float, col=(12, 14, 22), lantern: bool = True, rim=(255, 175, 95)) -> None:
    """A simple standing figure in a long coat and cap, optionally holding a lantern."""
    d = ImageDraw.Draw(img, "RGBA")
    head = h * 0.075
    top = base - h
    d.polygon([(cx - h * 0.13, base), (cx + h * 0.13, base), (cx + h * 0.10, top + h * 0.17), (cx + h * 0.075, top + h * 0.14),
               (cx - h * 0.075, top + h * 0.14), (cx - h * 0.10, top + h * 0.17)], fill=col)
    d.ellipse([cx - head, top, cx + head, top + head * 2], fill=col)
    d.rectangle([cx - head * 1.15, top + head * 0.25, cx + head * 1.15, top + head * 0.7], fill=col)       # cap
    d.line([(cx + h * 0.08, top + h * 0.2), (cx + h * 0.17, top + h * 0.39)], fill=col, width=int(h * 0.04))
    if lantern:
        lx, ly = cx + h * 0.17, top + h * 0.42
        d.rectangle([lx - h * 0.025, ly, lx + h * 0.025, ly + h * 0.06], fill=(255, 214, 140, 255))
        glow(img, lx, ly + h * 0.03, h * 0.5, rim, 0.85)
    d.line([(cx - h * 0.095, top + h * 0.2), (cx - h * 0.08, top + h * 0.17)], fill=(*rim, 90), width=3)   # rim light


def fog(img: Image.Image, y0: float, y1: float, seed: int, alpha: int = 46) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d, rnd = ImageDraw.Draw(layer), random.Random(seed)
    for _ in range(26):
        x, y = rnd.random() * img.width, rnd.uniform(y0, y1)
        rw, rh = rnd.uniform(200, 520), rnd.uniform(26, 70)
        d.ellipse([x - rw, y - rh, x + rw, y + rh], fill=(190, 200, 215, alpha))
    img.paste(layer.filter(ImageFilter.GaussianBlur(38)), (0, 0), layer.filter(ImageFilter.GaussianBlur(38)))


def _finish(img: Image.Image, vig: float = 0.5, g: float = 0.04) -> Image.Image:
    return tag(grain(vignette(img, vig), g))


# ---- scenes -----------------------------------------------------------------------------------------------------------

def harbour(variant: int = 0, size=(W, H)) -> Image.Image:
    """Wide harbour at dusk."""
    img = gradient(W, H, (22, 28, 62), (236, 150, 90) if variant % 2 == 0 else (214, 128, 112))
    stars(img, 120, 0.4, 3 + variant)
    horizon = int(H * 0.60)
    glow(img, W * 0.64, horizon, 420, (255, 190, 120), 0.75)
    sea(img, horizon, (92, 70, 86), (14, 18, 36), 5 + variant)
    d = ImageDraw.Draw(img, "RGBA")
    lighthouse(img, W * 0.80, horizon + 30, H * 0.36, lit=True)
    for bx, by, s in ((W * 0.18, horizon + 52, 56), (W * 0.33, horizon + 80, 74), (W * 0.52, horizon + 44, 40), (W * 0.42, horizon + 120, 96)):
        boat(d, bx, by, s)
    d.polygon([(0, H * 0.90), (W, H * 0.86), (W, H), (0, H)], fill=(9, 11, 18))
    fog(img, horizon - 10, horizon + 60, 9 + variant, 38)
    return _finish(img.resize(size) if size != (W, H) else img)


def quay(variant: int = 0, size=(W, H)) -> Image.Image:
    img = gradient(W, H, (18, 24, 52), (222, 138, 92))
    stars(img, 80, 0.35, 11)
    horizon = int(H * 0.56)
    glow(img, W * 0.35, horizon, 380, (255, 186, 120), 0.7)
    sea(img, horizon, (86, 66, 84), (12, 16, 32), 13)
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(0, H * 0.80), (W, H * 0.76), (W, H), (0, H)], fill=(10, 12, 20))
    for bx in (W * 0.12, W * 0.86):
        d.rectangle([bx - 14, H * 0.74, bx + 14, H * 0.82], fill=(10, 12, 20))
    figure(img, W * (0.55 + 0.02 * variant), H * 0.86, H * 0.62)
    return _finish(img, 0.55)


def stairs(variant: int = 0, size=(W, H)) -> Image.Image:
    img = Image.new("RGB", (W, H), (8, 10, 18))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W * 0.5, H * 0.52
    for i in range(34):
        a = i * 0.34 + variant * 0.2
        r0, r1 = 70 + i * 17, 150 + i * 17
        x0, y0 = cx + math.cos(a) * r0, cy + math.sin(a) * r0 * 0.46
        x1, y1 = cx + math.cos(a) * r1, cy + math.sin(a) * r1 * 0.46
        shade = int(30 + 90 * (1 - i / 34))
        d.line([(x0, y0), (x1, y1)], fill=(shade + 40, shade + 14, shade - 14, 255), width=int(10 + i * 0.7))
    for r in (60, 140, 320, 560):
        d.ellipse([cx - r, cy - r * 0.46, cx + r, cy + r * 0.46], outline=(70, 60, 56, 90), width=3)
    glow(img, cx, cy, 640, (255, 170, 90), 0.85 if variant == 0 else 0.55)
    return _finish(img, 0.62)


def rail(variant: int = 0, size=(W, H)) -> Image.Image:
    img = gradient(W, H, (14, 22, 48), (40, 56, 90))
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(21)
    for _ in range(40):                                          # out-of-focus window lights
        x, y, r = rnd.random() * W, rnd.random() * H * 0.7, rnd.uniform(20, 80)
        glow(img, x, y, r, (120, 160, 230) if rnd.random() < .6 else (255, 190, 120), 0.35)
    d.polygon([(0, H * 0.62), (W, H * 0.52), (W, H * 0.60), (0, H * 0.72)], fill=(14, 16, 24))
    d.polygon([(W * 0.42, H * 0.64), (W * 0.60, H * 0.60), (W * 0.64, H * 0.70), (W * 0.46, H * 0.76)], fill=(10, 12, 18))   # hand
    glow(img, W * 0.55, H * 0.66, 360, (255, 180, 100), 0.45)
    return _finish(img, 0.6)


def lamp_room(variant: int = 0, size=(W, H)) -> Image.Image:
    img = Image.new("RGB", (W, H), (7, 9, 16))
    cx, cy = W * 0.5, H * 0.48
    glow(img, cx, cy, 900, (255, 176, 84), 0.9 if variant == 0 else 0.6)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(1, 9):
        r = 40 + i * 52
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 214, 150, max(30, 190 - i * 18)), width=3)
    for k in range(16):
        a = k * math.pi / 8
        d.line([(cx + math.cos(a) * 60, cy + math.sin(a) * 60), (cx + math.cos(a) * 440, cy + math.sin(a) * 440)], fill=(255, 220, 160, 70), width=2)
    glow(img, cx, cy, 120, (255, 240, 200), 1.0)
    for x in (W * 0.08, W * 0.92):
        d.rectangle([x - 26, 0, x + 26, H], fill=(10, 12, 18))
    d.rectangle([0, H * 0.88, W, H], fill=(10, 12, 18))
    return _finish(img, 0.55)


def beam(variant: int = 0, size=(W, H)) -> Image.Image:
    img = gradient(W, H, (6, 10, 28), (18, 30, 62))
    stars(img, 220, 0.6, 31)
    horizon = int(H * 0.62)
    sea(img, horizon, (22, 36, 66), (6, 10, 22), 33, shimmer=(255, 220, 160))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon([(W * 0.10, H * 0.30), (W, H * 0.12), (W, H * 0.46)], fill=(255, 230, 170, 78))
    layer = layer.filter(ImageFilter.GaussianBlur(26))
    img.paste(layer, (0, 0), layer)
    lighthouse(img, W * 0.10, H * 0.88, H * 0.58, lit=True)
    return _finish(img, 0.5)


def desk(variant: int = 0, size=(W, H)) -> Image.Image:
    img = gradient(W, H, (30, 22, 20), (14, 10, 10))
    glow(img, W * 0.5, H * 0.45, 760, (255, 180, 96), 0.7)
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(W * 0.24, H * 0.30), (W * 0.50, H * 0.26), (W * 0.50, H * 0.76), (W * 0.24, H * 0.80)], fill=(224, 208, 176, 255))
    d.polygon([(W * 0.50, H * 0.26), (W * 0.76, H * 0.30), (W * 0.76, H * 0.80), (W * 0.50, H * 0.76)], fill=(214, 196, 162, 255))
    for i in range(14):
        y = H * (0.34 + i * 0.031)
        d.line([(W * 0.28, y), (W * 0.47, y - 4)], fill=(80, 64, 50, 190), width=2)
        d.line([(W * 0.54, y - 4), (W * 0.72, y)], fill=(80, 64, 50, 190), width=2)
    return _finish(img, 0.55)


FRAMES = {"harbour": harbour, "quay": quay, "stairs": stairs, "rail": rail, "lamp": lamp_room, "beam": beam, "desk": desk}


def keeper_portrait(version: int = 1) -> Image.Image:
    w, h = 832, 1248
    img = gradient(w, h, (18, 26, 52), (52, 44, 66) if version == 1 else (60, 46, 58))
    glow(img, w * 0.5, h * 0.55, 520, (255, 170, 100), 0.35)
    stars(img, 60, 0.4, 41)
    figure(img, w * 0.5, h * 0.93, h * 0.84, col=(16, 18, 28), lantern=True)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([w * 0.34, h * 0.40, w * 0.66, h * 0.43], fill=(*(150, 120, 80), 130))                       # scarf line
    return _finish(img.convert("RGB"), 0.45, 0.03)


def lantern_prop() -> Image.Image:
    s = 1024
    img = gradient(s, s, (20, 20, 28), (8, 8, 14))
    glow(img, s / 2, s * 0.52, 420, (255, 176, 90), 0.9)
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(s * 0.36, s * 0.78), (s * 0.64, s * 0.78), (s * 0.60, s * 0.30), (s * 0.40, s * 0.30)], fill=(255, 214, 140, 235), outline=(30, 24, 20, 255))
    d.polygon([(s * 0.34, s * 0.30), (s * 0.66, s * 0.30), (s * 0.5, s * 0.18)], fill=(24, 22, 26, 255))
    d.rectangle([s * 0.34, s * 0.78, s * 0.66, s * 0.83], fill=(24, 22, 26, 255))
    d.arc([s * 0.40, s * 0.06, s * 0.60, s * 0.30], 180, 360, fill=(24, 22, 26, 255), width=10)
    for x in (0.45, 0.5, 0.55):
        d.line([(s * x, s * 0.30), (s * (0.5 + (x - 0.5) * 1.3), s * 0.78)], fill=(40, 30, 24, 160), width=4)
    return _finish(img, 0.35, 0.03)


def location_wide() -> Image.Image:
    return harbour(0, (1424, 800))
