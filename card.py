"""Shareable "战绩卡" — portrait Card 2.0 (小红书 3:4 default).

Engineered for the half-second cold glance: the TIER TITLE (齐天大圣…) reads as
an identity before any number. Monthly burn is framed as operating SCALE; the
西游记 ascension ladder shows how high you've climbed and what's above; lifetime
is the never-resets trophy; the dollar figure is demoted; a "本地日志核验" mark
keeps the number credible. Two handles (X + 小红书号) tether it to a real person.

Premium type: SF Compact Black (display numbers), Avenir (Latin labels),
Hiragino Sans GB (CJK — PingFang isn't Pillow-loadable). Pure stdlib + Pillow.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import badges
import core

W, H = 1080, 1440          # 小红书 3:4 portrait
PAD = 84
CX = W // 2
OUT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".card-out", "tokenpulse-card.png")

BG = (12, 15, 20)
BG2 = (22, 27, 36)
INK = (238, 242, 247)
DIM = (146, 155, 166)
FAINT = (96, 105, 116)
HEAT = (249, 146, 62)
GOLD = (242, 198, 102)
TRACK = (34, 39, 48)
CHIP = (27, 32, 41)
ROW = (20, 24, 32)

SANS = "/System/Library/Fonts/Helvetica.ttc"
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"           # idx0 = Bold
AVENIR_BOOK = "/System/Library/Fonts/Avenir.ttc"           # idx0 = Book
SFCOMPACT = "/System/Library/Fonts/SFCompact.ttf"          # Black weight
HAN = "/System/Library/Fonts/Hiragino Sans GB.ttc"         # idx0 W3, idx2 W6
EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE = 160


def _f(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.truetype(SANS, size)


def _disp(size):
    return _f(SFCOMPACT, size)


def _av(size, bold=True):
    return _f(AVENIR, size) if bold else _f(AVENIR_BOOK, size)


def _han(size, bold=False):
    return _f(HAN, size, index=2 if bold else 0)


def _emoji(char, px):
    try:
        f = ImageFont.truetype(EMOJI, EMOJI_STRIKE)
        im = Image.new("RGBA", (EMOJI_STRIKE + 40, EMOJI_STRIKE + 40), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((20, 10), char, font=f, embedded_color=True)
        im = im.crop(im.getbbox() or (0, 0, EMOJI_STRIKE, EMOJI_STRIKE))
        s = px / im.height
        return im.resize((max(1, int(im.width * s)), px), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None


def _tok(n):
    n = n or 0
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.0f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return str(int(n))


def _usd(n):
    return "$" + f"{round(n or 0):,}"


def _glow(size, xy, radius, color, alpha):
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius],
                              fill=color + (alpha,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.5))


def _spaced(d, xy, text, font, fill, tracking, anchor="l"):
    """Letter-spaced text (premium uppercase labels)."""
    widths = [d.textlength(c, font=font) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = xy[0] if anchor == "l" else xy[0] - total / 2 if anchor == "c" else xy[0] - total
    for c, w in zip(text, widths):
        d.text((x, xy[1]), c, font=font, fill=fill)
        x += w + tracking
    return total


def _ct(d, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text((CX - w / 2, y), text, font=font, fill=fill)
    return w


def _segrow(d, img, y, segs, gap=12):
    """Center a row of mixed segments: ('t',text,font,fill) or ('e',emoji,px)."""
    ws = []
    for s in segs:
        ws.append((_emoji(s[1], s[2]).width if s[0] == "e" and _emoji(s[1], s[2]) else
                   (0 if s[0] == "e" else d.textlength(s[1], font=s[2]))))
    total = sum(ws) + gap * (len(segs) - 1)
    x = CX - total / 2
    for s, w in zip(segs, ws):
        if s[0] == "e":
            e = _emoji(s[1], s[2])
            if e:
                img.alpha_composite(e, (int(x), int(y)))
        else:
            d.text((x, y), s[1], font=s[2], fill=s[3])
        x += w + gap
    return total


def _check(d, x, y, color):
    d.line([(x, y + 6), (x + 4, y + 10), (x + 11, y)], fill=color, width=2)


def _git_handle():
    import subprocess
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=2).stdout.strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


def render(data, out_path=OUT_DEFAULT, date_str=""):
    tier = data["tier"]
    life = data.get("lifetime") or {}
    handles = data.get("handles") or {}
    rs = data.get("rank_self") or {}
    x_handle = (handles.get("x") or "").lstrip("@")
    xhs = (handles.get("xhs") or "").strip()

    img = Image.new("RGB", (W, H), BG)
    img = img.convert("RGBA")
    img.alpha_composite(_glow((W, H), (CX, 56), 540, HEAT, 58))
    img.alpha_composite(_glow((W, H), (CX, 56), 280, HEAT, 34))
    d = ImageDraw.Draw(img)

    # ── HEADER: creature + tier title + gloss + handles ──
    creature = _emoji(tier["emoji"], 138)
    if creature:
        img.alpha_composite(creature, (CX - creature.width // 2, 70))
    _ct(d, 222, tier["name"], _han(86, bold=True), HEAT)
    _spaced(d, (CX, 318), tier["name_en"].upper(), _av(24), GOLD, 7, anchor="c")
    segs = []
    if x_handle:
        segs.append(("t", f"@{x_handle}", _av(22, bold=False), INK))
    if x_handle and xhs:
        segs.append(("t", "·", _av(22), FAINT))
    if xhs:
        segs.append(("e", "📕", 20))
        segs.append(("t", xhs, _han(21), INK))
    if segs:
        _segrow(d, img, 356, segs, gap=13)

    # ── HERO NUMBER ──
    _spaced(d, (CX, 432), "THIS MONTH", _av(23), DIM, 5, anchor="c")
    num = _tok(data["monthly_tokens"])
    big = _disp(196)
    nw = d.textlength(num, font=big)
    d.text((CX - nw / 2, 458), num, font=big, fill=INK)
    _ct(d, 658, "tokens · 本月燃烧吞吐", _han(24), DIM)

    # ── RANK slot (honest) ──
    rank_main = data.get("rank_text") or "创始操作者 #1"
    _spaced(d, (CX, 720), "RANK", _av(22), DIM, 5, anchor="c")
    _ct(d, 748, rank_main, _han(38, bold=True), GOLD)
    peak = (rs.get("peak_day") or {}).get("total", 0)
    _ct(d, 802, f"历史巅峰 {_tok(peak)}/日   ·   最佳30天 {_tok(rs.get('best_30d', 0))}", _han(20), DIM)

    # ── ASCENSION LADDER (centerpiece) ──
    lx, lw = PAD, W - 2 * PAD
    top, rh = 866, 41
    cur = tier["name"]
    climbed = False  # rows below current are "climbed"
    for i, (thr, emoji, cn, en, blurb) in enumerate(badges.SAGA_TIERS):  # descending: 如来 first
        ry = top + i * rh
        is_cur = (cn == cur)
        if is_cur:
            d.rounded_rectangle([lx - 12, ry - 3, lx + lw + 12, ry + rh - 7], radius=10, fill=(48, 37, 22))
        ec = _emoji(emoji, 25)
        if ec:
            img.alpha_composite(ec, (lx + 2, ry + 3))
        name_fill = HEAT if is_cur else (DIM if climbed else INK)
        nf = _han(23, bold=is_cur)
        d.text((lx + 42, ry + 2), cn, font=nf, fill=name_fill)
        d.text((lx + 42 + d.textlength(cn, font=nf) + 12, ry + 8), en, font=_av(15, bold=False), fill=FAINT)
        thr_txt = f"{_tok(thr)}+" if thr > 0 else "起步"
        tf = _av(19) if thr > 0 else _han(18)
        tw = d.textlength(thr_txt, font=tf)
        d.text((lx + lw - tw, ry + 4), thr_txt, font=tf, fill=GOLD if is_cur else FAINT)
        if is_cur:
            mk = "你在此"
            mkw = d.textlength(mk, font=_han(17))
            d.polygon([(lx + lw - tw - 24, ry + 9), (lx + lw - tw - 24, ry + 21),
                       (lx + lw - tw - 16, ry + 15)], fill=HEAT)
            d.text((lx + lw - tw - 30 - mkw, ry + 7), mk, font=_han(17), fill=HEAT)
        elif climbed:
            _check(d, lx + lw - tw - 26, ry + 6, (88, 132, 96))
        if is_cur:
            climbed = True

    # ── LIFETIME ──
    ly = top + len(badges.SAGA_TIERS) * rh + 22
    le = _emoji("♾️", 23)
    if le:
        img.alpha_composite(le, (PAD, ly + 3))
    lt = f"生涯 {_tok(life.get('lifetime_tokens', 0))}"
    d.text((PAD + 34, ly), lt, font=_han(27, bold=True), fill=GOLD)
    since = (life.get("first_use_date") or "")[:7]
    d.text((PAD + 34 + d.textlength(lt, font=_han(27, bold=True)) + 16, ly + 6),
           f"自 {since} · {life.get('days_active', 0)} 天在线", font=_han(19), fill=DIM)

    # ── BADGES (single row, top 5) ──
    by = ly + 52
    cx = PAD
    for b in (data.get("badges") or [])[:5]:
        ce = _emoji(b["icon"], 21)
        label = b["name"]
        chw = int((ce.width + 7 if ce else 0) + d.textlength(label, font=_han(18)) + 28)
        if cx + chw > W - PAD:
            break
        fill = (48, 38, 24) if b.get("hero") else CHIP
        d.rounded_rectangle([cx, by, cx + chw, by + 36], radius=18, fill=fill)
        ix = cx + 13
        if ce:
            img.alpha_composite(ce, (int(ix), by + 7)); ix += ce.width + 7
        d.text((int(ix), by + 8), label, font=_han(18), fill=GOLD if b.get("hero") else INK)
        cx += chw + 10

    # ── FOOTER ──
    fy = H - 78
    d.line([(PAD, fy - 20), (W - PAD, fy - 20)], fill=TRACK, width=1)
    d.text((PAD, fy), f"≈ {_usd(data.get('monthly_cost'))} 算力 · 包月订阅吞吐", font=_han(18), fill=FAINT)
    ve = _emoji("✅", 16)
    vx = PAD
    if ve:
        img.alpha_composite(ve, (PAD, fy + 30)); vx = PAD + ve.width + 6
    d.text((vx, fy + 30), "本地日志核验 · 非自填", font=_han(16), fill=FAINT)
    wm = "TOKENPULSE"
    wmw = d.textlength(wm, font=_av(20))
    fe = _emoji("⏱", 18)
    fx = W - PAD - wmw
    if fe:
        img.alpha_composite(fe, (int(fx - fe.width - 7), fy - 2))
    d.text((fx, fy), wm, font=_av(20), fill=DIM)
    if date_str:
        d.text((W - PAD - d.textlength(date_str, font=_av(15, bold=False)), fy + 31), date_str,
               font=_av(15, bold=False), fill=FAINT)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path)
    return out_path


def make_card(out_path=OUT_DEFAULT, date_str=""):
    return render(badges.card_data(), out_path, date_str)


if __name__ == "__main__":
    print("wrote", make_card())
