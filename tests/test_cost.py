"""Tests for cost pricing logic (model mapping + cost math)."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import codexbar  # noqa: E402
import cost  # noqa: E402

PRICES = {
    "claude-opus-4-5": {"input": 5, "output": 25, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet-4-5": {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75},
    "gpt-5.5": {"input": 5, "output": 30, "cache_read": 0.5},
}


@pytest.fixture(autouse=True)
def isolated_cost_cache():
    old_cache = dict(cost._CACHE)
    cost._CACHE.clear()
    yield
    cost._CACHE.clear()
    cost._CACHE.update(old_cache)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _mtime(iso_ts):
    return datetime.fromisoformat(iso_ts).timestamp()


def _set_mtime(path, iso_ts):
    mtime = _mtime(iso_ts)
    os.utime(path, (mtime, mtime))


def test_price_exact_match():
    assert cost.price_for("gpt-5.5", PRICES)["input"] == 5


def test_price_strips_date_suffix():
    # "claude-opus-4-5-20251101" -> "claude-opus-4-5"
    assert cost.price_for("claude-opus-4-5-20251101", PRICES)["output"] == 25


def test_price_prefix_match():
    # unknown exact, but prefix of a known id
    r = cost.price_for("claude-sonnet-4-5-20250929", PRICES)
    assert r["input"] == 3


def test_price_unknown_returns_empty():
    assert cost.price_for("totally-unknown-model", PRICES) == {}


def test_cost_math_claude_style():
    rates = PRICES["claude-opus-4-5"]
    # 1M input, 2M cache_read, 0.5M cache_write, 0.1M output
    c = cost._cost(rates, 1_000_000, 500_000, 2_000_000, 100_000)
    expected = (1_000_000 * 5 + 500_000 * 6.25 + 2_000_000 * 0.5 + 100_000 * 25) / 1_000_000
    assert abs(c - expected) < 1e-9


def test_cost_empty_rates_is_zero():
    assert cost._cost({}, 1_000_000, 0, 0, 1_000_000) == 0.0


def test_claude_summary_sums_30d_today_dedupes_and_uses_latest_mtime(tmp_path, monkeypatch):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    today_path = tmp_path / "claude" / "today.jsonl"
    older_path = tmp_path / "claude" / "older.jsonl"
    old_outside_window = tmp_path / "claude" / "outside.jsonl"

    today_row = {
        "timestamp": "2026-06-13T10:00:00+00:00",
        "requestId": "req-today",
        "message": {
            "id": "msg-today",
            "model": "claude-opus-4-5",
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 10,
                "cache_read_input_tokens": 20,
                "output_tokens": 30,
            },
        },
    }
    _write_jsonl(today_path, [today_row, today_row])
    _write_jsonl(
        older_path,
        [
            {
                "timestamp": "2026-06-03T10:00:00+00:00",
                "requestId": "req-older",
                "message": {
                    "id": "msg-older",
                    "model": "claude-sonnet-4-5",
                    "usage": {
                        "input_tokens": 5,
                        "cache_creation_input_tokens": 6,
                        "cache_read_input_tokens": 7,
                        "output_tokens": 8,
                    },
                },
            }
        ],
    )
    _write_jsonl(
        old_outside_window,
        [
            {
                "timestamp": "2026-05-01T10:00:00+00:00",
                "requestId": "req-old",
                "message": {
                    "id": "msg-old",
                    "model": "claude-opus-4-5",
                    "usage": {"input_tokens": 999, "output_tokens": 999},
                },
            }
        ],
    )
    _set_mtime(today_path, "2026-06-13T12:00:00+00:00")
    _set_mtime(older_path, "2026-06-13T13:00:00+00:00")
    _set_mtime(old_outside_window, "2026-05-01T12:00:00+00:00")

    monkeypatch.setattr(cost, "_load_prices", lambda: PRICES)
    monkeypatch.setattr(
        cost.glob,
        "glob",
        lambda pattern, recursive=False: [str(today_path), str(older_path), str(old_outside_window)],
    )

    summary = cost._claude_summary(now)

    expected_today_cost = cost._cost(PRICES["claude-opus-4-5"], 100, 10, 20, 30)
    expected_older_cost = cost._cost(PRICES["claude-sonnet-4-5"], 5, 6, 7, 8)
    assert summary["tokens_today"] == 160
    assert summary["tokens_30d"] == 186
    assert summary["latest_tokens"] == 26
    assert summary["cost_today"] == pytest.approx(expected_today_cost)
    assert summary["cost_30d"] == pytest.approx(expected_today_cost + expected_older_cost)


def test_codex_summary_dedupes_sessions_sums_usage_and_uses_latest_mtime(tmp_path, monkeypatch):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    dup_uuid = "11111111-1111-4111-8111-111111111111"
    latest_uuid = "22222222-2222-4222-8222-222222222222"
    old_dup = tmp_path / "sessions" / f"rollout-a-{dup_uuid}.jsonl"
    new_dup = tmp_path / "archived_sessions" / f"rollout-b-{dup_uuid}.jsonl"
    latest = tmp_path / "sessions" / f"rollout-c-{latest_uuid}.jsonl"

    _write_jsonl(
        old_dup,
        [
            {"timestamp": "2026-06-13T08:00:00+00:00", "payload": {"model": "gpt-5.5"}},
            {
                "timestamp": "2026-06-13T08:01:00+00:00",
                "payload": {
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 900,
                            "cached_input_tokens": 0,
                            "output_tokens": 100,
                            "total_tokens": 1000,
                        }
                    }
                },
            },
        ],
    )
    _write_jsonl(
        new_dup,
        [
            {"timestamp": "2026-06-13T09:00:00+00:00", "payload": {"model": "gpt-5.5"}},
            {
                "timestamp": "2026-06-13T09:01:00+00:00",
                "payload": {
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 25,
                            "output_tokens": 10,
                            "total_tokens": 110,
                        }
                    }
                },
            },
            {
                "timestamp": "2026-06-03T09:02:00+00:00",
                "payload": {
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 50,
                            "cached_input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 55,
                        }
                    }
                },
            },
        ],
    )
    _write_jsonl(
        latest,
        [
            {"timestamp": "2026-06-03T10:00:00+00:00", "payload": {"model": "gpt-5.5"}},
            {
                "timestamp": "2026-06-03T10:01:00+00:00",
                "payload": {
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 5,
                            "output_tokens": 2,
                            "total_tokens": 12,
                        }
                    }
                },
            },
        ],
    )
    _set_mtime(old_dup, "2026-06-13T11:00:00+00:00")
    _set_mtime(new_dup, "2026-06-13T12:00:00+00:00")
    _set_mtime(latest, "2026-06-13T13:00:00+00:00")

    def fake_glob(pattern, recursive=False):
        if "archived_sessions" in pattern:
            return [str(new_dup)]
        return [str(old_dup), str(latest)]

    monkeypatch.setattr(cost, "_load_prices", lambda: PRICES)
    monkeypatch.setattr(cost.glob, "glob", fake_glob)
    monkeypatch.setattr(cost.codexbar, "usage", lambda **_: {"available": False})

    summary = cost._codex_summary(now)

    expected_today_cost = cost._cost(PRICES["gpt-5.5"], 75, 0, 25, 10)
    expected_older_dup_cost = cost._cost(PRICES["gpt-5.5"], 40, 0, 10, 5)
    expected_latest_cost = cost._cost(PRICES["gpt-5.5"], 5, 0, 5, 2)
    assert summary["tokens_today"] == 110
    assert summary["tokens_30d"] == 177
    assert summary["latest_tokens"] == 12
    assert summary["cost_today"] == pytest.approx(expected_today_cost)
    assert summary["cost_30d"] == pytest.approx(
        expected_today_cost + expected_older_dup_cost + expected_latest_cost
    )


def test_codex_summary_matches_local_codexbar_when_available(monkeypatch):
    now = datetime(2026, 7, 22, 23, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cost.codexbar, "usage", lambda **_: {
        "available": True,
        "cost_today": 576.1155025,
        "cost_30d": 8640.73,
        "tokens_today": 825_620_085,
        "tokens_30d": 11_000_000_000,
        "cache_read_30d": 796_602_240,
        "input_30d": 823_195_581,
    })
    summary = cost._codex_summary(now)
    assert summary["tokens_today"] == 825_620_085
    assert summary["cost_today"] == pytest.approx(576.1155025)
    assert summary["latest_tokens"] == 825_620_085


def test_codexbar_parser_uses_requested_local_day():
    parsed = codexbar._parse([{
        "daily": [
            {"date": "2026-07-21", "totalTokens": 10, "totalCost": 1},
            {"date": "2026-07-22", "totalTokens": 825_620_085, "totalCost": 576.1155025},
        ],
        "totals": {"totalTokens": 11_000_000_000, "totalCost": 8640.73,
                   "cacheReadTokens": 796_602_240, "inputTokens": 823_195_581},
    }], datetime(2026, 7, 22).date())
    assert parsed["available"] is True
    assert parsed["tokens_today"] == 825_620_085
    assert parsed["tokens_30d"] == 11_000_000_000


def test_codexbar_retains_trusted_usage_on_transient_failure(monkeypatch):
    codexbar._CACHE.clear()
    codexbar._LAST_TRUSTED.clear()
    good = {"available": True, "source": "codexbar", "tokens_today": 825_620_085}
    codexbar._LAST_TRUSTED[1] = good
    monkeypatch.setattr(codexbar, "_find_executable", lambda: None)

    result = codexbar.usage(days=1, ttl=0)

    assert result["tokens_today"] == 825_620_085
    assert result["stale"] is True


def test_codexbar_finds_homebrew_install_without_shell_path(monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(codexbar.shutil, "which", lambda _: None)
    monkeypatch.setattr(codexbar.os.path, "isfile", lambda path: path == "/opt/homebrew/bin/codexbar")
    monkeypatch.setattr(codexbar.os, "access", lambda path, mode: path == "/opt/homebrew/bin/codexbar")

    assert codexbar._find_executable() == "/opt/homebrew/bin/codexbar"


def test_usage_summary_ttl_zero_bypasses_stale_cache(monkeypatch):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    stale = {
        "cost_today": 999,
        "cost_30d": 999,
        "tokens_today": 999,
        "tokens_30d": 999,
        "latest_tokens": 999,
    }
    fresh = {
        "cost_today": 1,
        "cost_30d": 2,
        "tokens_today": 3,
        "tokens_30d": 4,
        "latest_tokens": 5,
    }
    cost._CACHE["summary:claude"] = (cost.time.time(), stale)
    monkeypatch.setattr(cost, "_claude_summary", lambda current_now: fresh)

    assert cost.usage_summary("claude", now=now, ttl=0) == fresh


def test_humanize():
    assert cost.humanize_tokens(2_900_000_000) == "2.9B"
    assert cost.humanize_tokens(47_000_000) == "47M"
    assert cost.humanize_cost(2174.789) == "$2,174.79"


def test_cache_hit_rate():
    assert cost.cache_hit_rate(80, 100) == 0.8
    assert cost.cache_hit_rate(0, 0) == 0.0      # divide-by-zero guard
    assert cost.cache_hit_rate(150, 100) == 1.0  # clamp >100%
