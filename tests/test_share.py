"""Tests for QR/share-page handoff generation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import share  # noqa: E402


def _fake_ensure_server(root, port):
    root.mkdir(parents=True, exist_ok=True)
    return int(port or 8765)


def test_qr_data_uri_is_png():
    uri = share.qr_data_uri("https://example.com/tokenpulse", pixels=96)
    assert uri.startswith("data:image/png;base64,")


def test_pick_lan_ip_rejects_vpn_fakeip_prefers_real_wifi():
    # Clash/Surge fake-ip TUN gateway must lose to the real Wi-Fi IP, never become the QR
    assert share._pick_lan_ip(["198.18.0.1", "192.168.0.105"]) == "192.168.0.105"
    assert share._pick_lan_ip(["198.18.0.1"]) is None          # no false phone link
    assert share._pick_lan_ip(["10.0.0.5", "192.168.1.2"]) == "192.168.1.2"  # 192.168 wins


def test_is_private_lan_ranges():
    for ok in ("192.168.0.105", "10.1.2.3", "172.16.0.1", "172.31.255.1"):
        assert share._is_private_lan(ok), ok
    for bad in ("198.18.0.1", "100.64.0.1", "169.254.1.1", "172.32.0.1", "127.0.0.1", "", None):
        assert not share._is_private_lan(bad), bad


def test_build_share_payload_uses_reachable_lan_url(tmp_path, monkeypatch):
    monkeypatch.setattr(share, "_lan_ip", lambda: "192.168.1.77")  # deterministic LAN IP
    monkeypatch.setattr(share, "_ensure_server", _fake_ensure_server)
    card = tmp_path / "card.png"
    card.write_bytes(b"fake-png")
    cfg = {
        "builder": {
            "handle": "zinan92",
            "xhs_id": "337506137",
            "douyin_id": "douyin-demo",
            "url": "https://example.com/builder",
        },
        "share": {"mode": "local", "port": 0, "base_url": ""},
    }

    payload = share.build_share_payload(card, config=cfg, root=tmp_path / "share", start_tunnel=False)

    # the QR must point at a LAN IP a phone can reach — never localhost (dead link on a phone)
    assert payload["url"] == f"http://192.168.1.77:8765/{payload['share_id']}/"
    assert payload["local_url"] == payload["url"]
    assert payload["reachable"] == "lan"
    assert payload["https"] is False
    assert payload["qr"].startswith("data:image/png;base64,")
    page = tmp_path / "share" / payload["share_id"] / "index.html"
    copied = tmp_path / "share" / payload["share_id"] / "card.png"
    assert page.exists()
    assert copied.read_bytes() == b"fake-png"
    html = page.read_text(encoding="utf-8")
    assert "navigator.share" in html
    assert "复制文案" in html
    assert "小红书号：337506137" in html
    assert "抖音：douyin-demo" in html
    # og:image lets X unfurl the card image; must be the absolute card URL
    assert 'property="og:image"' in html
    assert "192.168.1.77" in html and "card.png" in html


def test_build_share_payload_local_fallback_when_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(share, "_lan_ip", lambda: None)  # no network → loopback (honest)
    monkeypatch.setattr(share, "_ensure_server", _fake_ensure_server)
    card = tmp_path / "card.png"
    card.write_bytes(b"x")
    cfg = {"builder": {}, "share": {"mode": "local", "port": 0, "base_url": ""}}
    payload = share.build_share_payload(card, config=cfg, root=tmp_path / "share", start_tunnel=False)
    assert payload["url"] == f"http://127.0.0.1:8765/{payload['share_id']}/"
    assert payload["local_url"] == payload["url"]
    assert payload["reachable"] == "local"


def test_build_share_payload_accepts_record_card_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(share, "_lan_ip", lambda: "192.168.1.77")
    monkeypatch.setattr(share, "_ensure_server", _fake_ensure_server)
    card = tmp_path / "record.png"
    card.write_bytes(b"record-png")
    cfg = {"builder": {}, "share": {"mode": "local", "port": 0, "base_url": ""}}

    payload = share.build_share_payload(
        card,
        config=cfg,
        root=tmp_path / "share",
        start_tunnel=False,
        title="TokenPulse 单日纪录卡",
        share_text="我刷新了 TokenPulse 单日 token 纪录。",
        filename="tokenpulse-record-card.png",
    )

    html = (tmp_path / "share" / payload["share_id"] / "index.html").read_text(encoding="utf-8")
    assert payload["title"] == "TokenPulse 单日纪录卡"
    assert payload["filename"] == "tokenpulse-record-card.png"
    assert "TokenPulse 单日纪录卡" in html
    assert "我刷新了 TokenPulse 单日 token 纪录。" in html
    assert 'download="tokenpulse-record-card.png"' in html
