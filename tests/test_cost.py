"""Tests for cost pricing logic (model mapping + cost math)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cost  # noqa: E402

PRICES = {
    "claude-opus-4-5": {"input": 5, "output": 25, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet-4-5": {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75},
    "gpt-5.5": {"input": 5, "output": 30, "cache_read": 0.5},
}


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


def test_humanize():
    assert cost.humanize_tokens(2_900_000_000) == "2.9B"
    assert cost.humanize_tokens(47_000_000) == "47M"
    assert cost.humanize_cost(2174.789) == "$2,174.79"
