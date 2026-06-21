"""Shareable "value card" PNG — the social-flex artifact.

Renders the egg tier + monthly burn + $ + streak + 30-day sparkline + badges
into a clean dark card (Pillow), designed to be screenshot-worthy. The
contrarian number ("$5,729 burned from a flat fee") is the hook.

Used by the widget's Share button and (optionally) Telegram. Pure stdlib + Pillow.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import badges
import core

W, H = 1000, 560
PAD = 56
OUT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".card-out", "tokenpulse-card.png")

BG = (13, 17, 23)
BG2 = (24, 29, 38)
INK = (235, 240, 246)
DIM = (139, 148, 158)
FAINT = (94, 103, 111)
HEAT = (249, 146, 62)
TRACK = (38, 43, 52)

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160  # the Apple Color Emoji bitmap size Pillow accepts


def _font(path, size):
    return ImageFont.truetype(path, size)


def _emoji(char: str, px: int) -> Image.Image | None:
    """Render an emoji glyph to an RGBA image of ~px height."""
    try:
        f = ImageFont.truetype(EMOJI, EMOJI_STRIKE)
        im = Image.new("RGBA", (EMOJI_STRIKE + 40, EMOJI_STRIKE + 40), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20, 10), char, font=f, embedded_color=True)
        im = im.crop(im.getbbox() or (0, 0, EMOJI_STRIKE, EMOJI_STRIKE))
        scale = px / im.height
        return im.resize((max(1, int(im.width * scale)), px), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None


def _tok(n: int) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.0f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return str(int(n))


def _usd(n: float) -> str:
    return "$" + f"{round(n):,}"


def _glow(size, xy, radius, color, alpha):
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse(
        [xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius],
        fill=color + (alpha,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.55))


def render(data: dict, out_path: str = OUT_DEFAULT, handle: str | None = None) -> str:
    handle = handle or core.load_config().get("handle") or "you"
    if not handle.startswith("@"):
        handle = "@" + handle

    img = Image.new("RGB", (W, H), BG)
    # heat glow top-right + faint base gradient
    img.paste(BG2, (0, 0, W, 150))
    img = img.convert("RGBA")
    img.alpha_composite(_glow((W, H), (W - 120, -40), 460, HEAT, 70))
    d = ImageDraw.Draw(img)

    tier = data["tier"]
    # ── tier badge (emoji + name) ──
    em = _emoji(tier["emoji"], 116)
    tx = PAD
    if em:
        img.alpha_composite(em, (PAD, 52))
        tx = PAD + em.width + 22
    d.text((tx, 64), tier["name"].upper(), font=_font(SANS, 34), fill=HEAT)
    d.text((tx, 110), handle, font=_font(SANS, 19), fill=DIM)
    # progress to next tier (top-right)
    if tier.get("next") and tier.get("progress_to_next") is not None:
        nlabel = f"{round(tier['progress_to_next'] * 100)}% to {tier['next']['name']}"
        w = d.textlength(nlabel, font=_font(SANS, 17))
        d.text((W - PAD - w, 72), nlabel, font=_font(SANS, 17), fill=DIM)

    # ── headline: monthly tokens ──
    big = _font(MONO, 96)
    num = _tok(data["monthly_tokens"])
    d.text((PAD, 178), num, font=big, fill=INK)
    nw = d.textlength(num, font=big)
    d.text((PAD + nw + 16, 240), "tokens", font=_font(SANS, 30), fill=DIM)
    d.text((PAD + nw + 16, 200), "this month", font=_font(SANS, 22), fill=FAINT)
    d.text((PAD, 290), f"≈ {_usd(data['monthly_cost'])} of compute burned on a flat subscription",
           font=_font(SANS, 22), fill=HEAT)

    # ── 30-day sparkline ──
    sx, sy, sw, sh = PAD, 350, W - 2 * PAD, 96
    series = data["series"] or [0]
    tgt = data["combined_target"] or 1
    mx = max(tgt, max(series)) or 1
    n = len(series)
    gap = 3
    bw = (sw - (n - 1) * gap) / n
    ty = sy + sh - sh * (tgt / mx)
    for i in range(0, W - PAD, 16):  # dashed target line
        d.line([(sx + (i - sx), ty), (min(sx + sw, sx + (i - sx) + 8), ty)], fill=FAINT, width=1)
    for i, v in enumerate(series):
        bx = int(sx + i * (bw + gap))
        bh = int(max(2, sh * (v / mx)))
        hit = v >= tgt
        d.rounded_rectangle([bx, int(sy + sh - bh), int(bx + bw), sy + sh], radius=2,
                            fill=HEAT if hit else TRACK)
    d.text((sx, sy + sh + 8),
           f"30 days   ·   hit {data['hit_days']}/{data['total_days']}   ·   "
           f"avg {_tok(data['avg'])}   ·   best {_tok((data['best_day'] or {}).get('total', 0))}",
           font=_font(SANS, 15), fill=FAINT)

    # ── streak + badges row ──
    by = 492
    chips = []
    if data["streak"] > 0:
        chips.append(("🔥", f"{data['streak']}-day streak"))
    for b in data["badges"]:
        if "streak" not in b["label"]:
            chips.append((b["icon"], b["label"]))
    cx = PAD
    for icon, label in chips[:4]:
        ce = _emoji(icon, 20)
        chw = int((ce.width + 6 if ce else 0) + d.textlength(label, font=_font(SANS, 16)) + 28)
        d.rounded_rectangle([cx, by, cx + chw, by + 32], radius=16, fill=(28, 33, 42))
        ix = cx + 12
        if ce:
            img.alpha_composite(ce, (int(ix), by + 6)); ix += ce.width + 6
        d.text((int(ix), by + 7), label, font=_font(SANS, 16), fill=INK)
        cx += chw + 10

    # ── footer wordmark ──
    fe = _emoji("⏱", 16)
    fx = PAD
    if fe:
        img.alpha_composite(fe, (PAD, H - 35)); fx = PAD + fe.width + 6
    d.text((fx, H - 34), "TOKENPULSE", font=_font(SANS, 15), fill=DIM)
    link = "github.com/zinan92/tokenpulse"
    lw = d.textlength(link, font=_font(SANS, 14))
    d.text((W - PAD - lw, H - 33), link, font=_font(SANS, 14), fill=FAINT)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path)
    return out_path


def make_card(out_path: str = OUT_DEFAULT, handle: str | None = None) -> str:
    return render(badges.card_data(), out_path, handle)


if __name__ == "__main__":
    print("wrote", make_card())
