"""Share-card handoff: QR generation, static mobile page, optional HTTPS tunnel.

The desktop widget is local, but phones need a URL. This module builds a small
static share page beside the PNG, serves `.card-out/share/` locally, and, when
available, exposes it through a temporary cloudflared HTTPS tunnel.
"""
from __future__ import annotations

import base64
import functools
import html
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import qrcode
from PIL import Image

import core

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / ".card-out" / "share"

_SERVER = None
_SERVER_ROOT: Path | None = None
_SERVER_PORT: int | None = None
_TUNNEL_PROC: subprocess.Popen | None = None
_TUNNEL_URL: str | None = None
_LOCK = threading.Lock()


def qr_pil(url: str, pixels: int = 220) -> Image.Image:
    """Return a square QR code image for `url`."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111820", back_color="#f8fafc").convert("RGB")
    return img.resize((pixels, pixels), Image.Resampling.NEAREST)


def qr_data_uri(url: str, pixels: int = 220) -> str:
    buf = io.BytesIO()
    qr_pil(url, pixels).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _share_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: D401
        return


def _lan_ip() -> str | None:
    """Best-effort LAN IP a phone on the same Wi-Fi can reach (None if offline)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return ip if ip and not ip.startswith("127.") else None


def _ensure_server(root: Path, port: int) -> int:
    """Serve `root` on ALL interfaces so a same-Wi-Fi phone (not just localhost)
    can reach it. Returns the bound port."""
    global _SERVER, _SERVER_ROOT, _SERVER_PORT
    root = root.resolve()
    with _LOCK:
        if _SERVER is not None and _SERVER_ROOT == root and _SERVER_PORT:
            return _SERVER_PORT
        root.mkdir(parents=True, exist_ok=True)
        chosen = int(port or 0)
        handler = functools.partial(_QuietHandler, directory=str(root))
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", chosen), handler)
        except OSError:
            httpd = ThreadingHTTPServer(("0.0.0.0", _free_port("0.0.0.0")), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _SERVER = httpd
        _SERVER_ROOT = root
        _SERVER_PORT = int(httpd.server_address[1])
        return _SERVER_PORT


def _read_tunnel(proc: subprocess.Popen):
    global _TUNNEL_URL
    assert proc.stdout is not None
    pat = re.compile(r"https://[-a-zA-Z0-9.]+trycloudflare\.com")
    for line in proc.stdout:
        m = pat.search(line)
        if m:
            with _LOCK:
                _TUNNEL_URL = m.group(0)


def _ensure_tunnel(local_url: str, timeout: float = 12.0) -> str | None:
    global _TUNNEL_PROC, _TUNNEL_URL
    if not shutil.which("cloudflared"):
        return None
    with _LOCK:
        if _TUNNEL_PROC is not None and _TUNNEL_PROC.poll() is None and _TUNNEL_URL:
            return _TUNNEL_URL
        _TUNNEL_URL = None
        _TUNNEL_PROC = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", local_url, "--no-autoupdate"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=_read_tunnel, args=(_TUNNEL_PROC,), daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _LOCK:
            if _TUNNEL_URL:
                return _TUNNEL_URL
            if _TUNNEL_PROC is not None and _TUNNEL_PROC.poll() is not None:
                return None
        time.sleep(0.2)
    return None


def _copy_card(card_path: str | os.PathLike, dest: Path):
    src = Path(card_path)
    if not src.exists():
        raise FileNotFoundError(str(src))
    shutil.copyfile(src, dest)


def _cleanup_old(root: Path, ttl_hours: int | float):
    if not ttl_hours or ttl_hours <= 0 or not root.exists():
        return
    cutoff = time.time() - float(ttl_hours) * 3600
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
        except OSError:
            continue


def _page_html(*, title: str, x_via: str, builder_url: str, douyin_id: str, xhs_id: str,
               card_url: str = "") -> str:
    safe_title = html.escape(title)
    safe_xhs = html.escape(xhs_id or "")
    safe_douyin = html.escape(douyin_id or "")
    safe_card = html.escape(card_url or "card.png")
    js = {
        "title": title,
        "text": "我用 TokenPulse 生成了一张 AI token 战绩卡。",
        "xVia": x_via,
        "builderUrl": builder_url,
    }
    js_blob = json.dumps(js, ensure_ascii=False)
    x_url = "https://x.com/intent/tweet?text=" + quote("我用 TokenPulse 生成了一张 AI token 战绩卡") + "&url="
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="我用 TokenPulse 生成了一张 AI token 战绩卡。">
<meta property="og:image" content="{safe_card}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{safe_card}">
<style>
  :root {{ color-scheme: dark; --bg:#0c1017; --ink:#f2f5f8; --muted:#8f98a5; --heat:#f9923e; --line:#252b36; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif; }}
  main {{ width:min(560px,100%); margin:0 auto; padding:18px 16px 28px; }}
  .card {{ width:100%; border-radius:14px; display:block; box-shadow:0 18px 44px #0008; }}
  h1 {{ font-size:18px; margin:16px 0 4px; }}
  p {{ color:var(--muted); margin:0 0 14px; }}
  .actions {{ display:grid; gap:10px; margin:16px 0; }}
  button,a {{ min-height:46px; border-radius:10px; border:1px solid var(--line); padding:12px 14px;
    background:#151a23; color:var(--ink); font-weight:700; text-align:center; text-decoration:none; }}
  button.primary {{ background:var(--heat); color:#1d1104; border-color:transparent; }}
  .hint {{ font-size:13px; color:var(--muted); border-top:1px solid var(--line); padding-top:14px; }}
</style>
</head>
<body>
<main>
  <img class="card" src="card.png" alt="TokenPulse 战绩卡">
  <h1>TokenPulse 战绩卡</h1>
  <p>先分享图片；如果系统不支持文件分享，就保存图片后打开目标平台发布。</p>
  <div class="actions">
    <button class="primary" id="share">分享图片</button>
    <a href="card.png" download="tokenpulse-card.png">保存图片</a>
    <button id="copy">复制文案</button>
    <a id="xlink" href="{x_url}" rel="noopener">发到 X</a>
    <a href="https://www.xiaohongshu.com/" rel="noopener">打开小红书</a>
    <a href="https://www.douyin.com/" rel="noopener">打开抖音</a>
  </div>
  <div class="hint">
    小红书号：{safe_xhs or "保存图片后发布"}<br>
    抖音：{safe_douyin or "保存图片后发布"}<br>
    Made with TokenPulse by <a href="{html.escape(builder_url)}" rel="noopener">@{html.escape(x_via)}</a>
  </div>
</main>
<script>
const SHARE = {js_blob};
const x = document.getElementById("xlink");
x.href = x.href + encodeURIComponent(location.href) + "&via=" + encodeURIComponent(SHARE.xVia || "zinan92") + "&hashtags=TokenPulse";
document.getElementById("share").addEventListener("click", async () => {{
  try {{
    const res = await fetch("card.png");
    const blob = await res.blob();
    const file = new File([blob], "tokenpulse-card.png", {{type: blob.type || "image/png"}});
    if (navigator.canShare && navigator.canShare({{files:[file]}})) {{
      await navigator.share({{title: SHARE.title, text: SHARE.text, files:[file]}});
      return;
    }}
    if (navigator.share) {{
      await navigator.share({{title: SHARE.title, text: SHARE.text, url: location.href}});
      return;
    }}
  }} catch (e) {{}}
  alert("这个浏览器不能直接分享图片。请长按图片保存，再打开目标平台发布。");
}});
document.getElementById("copy").addEventListener("click", async () => {{
  const text = `${{SHARE.text}}\n${{location.href}}`;
  try {{
    await navigator.clipboard.writeText(text);
    alert("已复制文案和链接。");
  }} catch (e) {{
    prompt("复制文案", text);
  }}
}});
</script>
</body>
</html>
"""


def build_share_payload(
    card_path: str | os.PathLike,
    config: dict | None = None,
    *,
    root: Path = OUT_ROOT,
    start_tunnel: bool = True,
) -> dict:
    config = config or core.load_config()
    share_cfg = config.get("share") if isinstance(config.get("share"), dict) else {}
    builder = config.get("builder") if isinstance(config.get("builder"), dict) else {}
    _cleanup_old(root, share_cfg.get("ttl_hours", 24))
    sid = _share_id()
    page_dir = root / sid
    page_dir.mkdir(parents=True, exist_ok=True)
    _copy_card(card_path, page_dir / "card.png")
    handle = (builder.get("handle") or "zinan92").lstrip("@")
    builder_url = builder.get("url") or core.DEFAULT_CONFIG["builder"]["url"]
    port = int(share_cfg.get("port") or 8765)
    bound_port = _ensure_server(root, port)            # listens on 0.0.0.0 (LAN-reachable)
    loopback = f"http://127.0.0.1:{bound_port}"         # cloudflared connects here
    lan_ip = _lan_ip()
    lan_base = f"http://{lan_ip}:{bound_port}" if lan_ip else loopback

    base_url = (os.environ.get("TOKENPULSE_SHARE_BASE_URL") or share_cfg.get("base_url") or "").rstrip("/")
    public_base = base_url
    mode = share_cfg.get("mode") or "cloudflared"
    if not public_base and start_tunnel and mode == "cloudflared":
        public_base = _ensure_tunnel(loopback) or ""
    base = public_base or lan_base                      # https tunnel > LAN http > loopback
    page_url = f"{base}/{sid}/"
    https = page_url.startswith("https://")

    # Write the page now the absolute card URL is known, so og:image lets X
    # unfurl the card image (only meaningful over the public https tunnel).
    (page_dir / "index.html").write_text(
        _page_html(
            title="TokenPulse 战绩卡",
            x_via=handle,
            builder_url=builder_url,
            douyin_id=builder.get("douyin_id") or "",
            xhs_id=builder.get("xhs_id") or "",
            card_url=f"{base}/{sid}/card.png",
        ),
        encoding="utf-8",
    )
    return {
        "url": page_url,
        "local_url": f"{lan_base}/{sid}/",
        "https": https,
        "qr": qr_data_uri(page_url),
        "share_id": sid,
        "page_dir": str(page_dir),
        "card": str(page_dir / "card.png"),
        "reachable": "https" if https else ("lan" if lan_ip else "local"),
        "mode": "https" if https else "local",
    }
