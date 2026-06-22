"""Shareable "战绩卡" PNG — the social-flex artifact (Card 2.0).

Engineered for the half-second cold glance: the TIER TITLE (齐天大圣…) and a
RANK read before any number. Monthly burn is framed as operating SCALE, the
dollar figure is demoted to a thin footer line, lifetime is the never-resets
trophy, and a "verified from local logs" mark keeps the number from reading as
typed-in vanity. Two handles (X + 小红书号) tether it to a real identity.

Pure stdlib + Pillow.
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
GOLD = (240, 196, 96)
TRACK = (38, 43, 52)
CHIP = (28, 33, 42)

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
HAN = "/System/Library/Fonts/Hiragino Sans GB.ttc"  # Pillow-loadable CJK (PingFang isn't)
EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(SANS, size)


def _han(size, bold=False):
    """CJK face — Hiragino Sans GB (idx 0 = W3 regular, idx 2 = W6 bold)."""
    try:
        return ImageFont.truetype(HAN, size, index=2 if bold else 0)
    except OSError:
        return ImageFont.truetype(SANS, size)


def _emoji(char: str, px: int):
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
    n = n or 0
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.0f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return str(int(n))


def _usd(n: float) -> str:
    return "$" + f"{round(n or 0):,}"


def _glow(size, xy, radius, color, alpha):
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius],
                              fill=color + (alpha,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.55))


def _git_handle():
    import subprocess
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


def _rt(d, xy, text, font, fill):
    """Right-anchored text at x=xy[0]."""
    w = d.textlength(text, font=font)
    d.text((xy[0] - w, xy[1]), text, font=font, fill=fill)
    return w


def render(data: dict, out_path: str = OUT_DEFAULT, date_str: str = "") -> str:
    tier = data["tier"]
    life = data.get("lifetime") or {}
    handles = data.get("handles") or {}
    x_handle = (handles.get("x") or "").lstrip("@")
    xhs = (handles.get("xhs") or "").strip()

    img = Image.new("RGB", (W, H), BG)
    img.paste(BG2, (0, 0, W, 156))
    img = img.convert("RGBA")
    img.alpha_composite(_glow((W, H), (W - 90, -30), 460, HEAT, 66))
    d = ImageDraw.Draw(img)

    # ── IDENTITY + TIER band (y0–156) ──
    creature = _emoji(tier["emoji"], 104)
    tx = PAD
    if creature:
        img.alpha_composite(creature, (PAD, 40))
        tx = PAD + creature.width + 22
    d.text((tx, 44), tier["name"], font=_han(52, bold=True), fill=HEAT)  # 齐天大圣
    d.text((tx, 110), f"{tier['name_en'].upper()} · 第二档", font=_font(SANS, 18), fill=DIM)
    # handles top-right (only if set; never auto-pull for the public card)
    hy = 50
    if x_handle:
        _rt(d, (W - PAD, hy), f"X   @{x_handle}", font=_font(SANS, 20), fill=INK); hy += 32
    if xhs:
        e = _emoji("📕", 19)
        label = f"小红书号  {xhs}"
        lw = d.textlength(label, font=_han(19)) + (e.width + 6 if e else 0)
        if e:
            img.alpha_composite(e, (int(W - PAD - lw), hy + 1))
        d.text((W - PAD - lw + (e.width + 6 if e else 0), hy), label, font=_han(19), fill=INK)

    # ── HERO (y170–300): monthly burn (left) + honest rank (right) ──
    d.text((PAD, 196), "本月燃烧 · THIS MONTH", font=_font(SANS, 17), fill=FAINT)
    num = _tok(data["monthly_tokens"])
    d.text((PAD, 220), num, font=_font(MONO, 84), fill=INK)
    nw = d.textlength(num, font=_font(MONO, 84))
    d.text((PAD + nw + 14, 272), "tokens", font=_font(SANS, 26), fill=DIM)

    rs = data.get("rank_self") or {}
    _rt(d, (W - PAD, 198), "战力榜 · RANK", font=_font(SANS, 17), fill=FAINT)
    _rt(d, (W - PAD, 222), "创始操作者 #1", font=_han(34), fill=GOLD)
    peak = (rs.get("peak_day") or {}).get("total", 0)
    _rt(d, (W - PAD, 270), f"历史巅峰 {_tok(peak)}/日  ·  最佳30天 {_tok(rs.get('best_30d', 0))}",
        font=_han(16), fill=DIM)

    # ── EVIDENCE (y316–430): lifetime trophy + ascension progress bar ──
    le = _emoji("♾️", 20)
    lx = PAD
    if le:
        img.alpha_composite(le, (PAD, 330)); lx = PAD + le.width + 8
    since = (life.get("first_use_date") or "")[:7]
    d.text((lx, 330), f"生涯 {_tok(life.get('lifetime_tokens', 0))}", font=_han(22), fill=GOLD)
    lw = d.textlength(f"生涯 {_tok(life.get('lifetime_tokens', 0))}", font=_han(22))
    d.text((lx + lw + 12, 335), f"自 {since} · {life.get('days_active', 0)} 天在线",
           font=_han(16), fill=DIM)

    # ascension bar: progress within current tier toward the next, summit marked
    bx, by, bw, bh = PAD, 384, W - 2 * PAD, 12
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, fill=TRACK)
    prog = tier.get("progress_to_next")
    if prog is not None:
        d.rounded_rectangle([bx, by, bx + int(bw * max(0.04, min(1, prog))), by + bh], radius=6, fill=HEAT)
    d.text((bx, by + 20), tier["name"], font=_han(15), fill=INK)
    if tier.get("next"):
        nlab = f"{tier['next']['name']} {_tok(tier['next']['at'])}   →   如来 10B 登顶"
        _rt(d, (bx + bw, by + 20), nlab, font=_han(15), fill=DIM)

    # ── BADGE strip (y446–488) ──
    by2 = 446
    cx = PAD
    for b in (data.get("badges") or [])[:5]:
        ce = _emoji(b["icon"], 19)
        label = b["name"]
        chw = int((ce.width + 6 if ce else 0) + d.textlength(label, font=_han(15)) + 26)
        if cx + chw > W - PAD:
            break
        fill = (44, 38, 24) if b.get("hero") else CHIP
        d.rounded_rectangle([cx, by2, cx + chw, by2 + 32], radius=16, fill=fill)
        ix = cx + 12
        if ce:
            img.alpha_composite(ce, (int(ix), by2 + 6)); ix += ce.width + 6
        d.text((int(ix), by2 + 7), label, font=_han(15), fill=GOLD if b.get("hero") else INK)
        cx += chw + 9

    # ── FOOTER (y506–560): demoted $, verified mark, wordmark ──
    d.line([(PAD, 500), (W - PAD, 500)], fill=TRACK, width=1)
    d.text((PAD, 514), f"≈ {_usd(data.get('monthly_cost'))} 算力 · 包月订阅吞吐",
           font=_han(14), fill=FAINT)
    ve = _emoji("✅", 14)
    vx = PAD
    vlabel = "本地日志核验"
    if ve:
        img.alpha_composite(ve, (PAD, 535)); vx = PAD + ve.width + 5
    d.text((vx, 534), vlabel, font=_han(13), fill=FAINT)
    foot = "⏱ TOKENPULSE"
    fe = _emoji("⏱", 15)
    fx = W - PAD - d.textlength("TOKENPULSE", font=_font(SANS, 15)) - (fe.width + 6 if fe else 0)
    if fe:
        img.alpha_composite(fe, (int(fx), 513))
    d.text((fx + (fe.width + 6 if fe else 0), 514), "TOKENPULSE", font=_font(SANS, 15), fill=DIM)
    if date_str:
        _rt(d, (W - PAD, 535), date_str, font=_font(SANS, 13), fill=FAINT)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path)
    return out_path


def make_card(out_path: str = OUT_DEFAULT, date_str: str = "") -> str:
    return render(badges.card_data(), out_path, date_str)


if __name__ == "__main__":
    print("wrote", make_card())
