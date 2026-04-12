"""Tests for diagnostic host normalization."""

from __future__ import annotations

import pytest

from core.host_sanitize import normalize_diagnostic_host


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8.8.8.8", "8.8.8.8"),
        ("1.1.1.1", "1.1.1.1"),
        ("2001:4860:4860::8888", "2001:4860:4860::8888"),
        ("[::1]", "[::1]"),
        ("example.com", "example.com"),
        ("my-router.local", "my-router.local"),
        ("a-b.example.net", "a-b.example.net"),
    ],
)
def test_accepts_valid_hosts(raw: str, expected: str) -> None:
    assert normalize_diagnostic_host(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "evil;rm -rf /",
        "a b",
        "../etc",
        "host;foo",
        "toolong" * 50,
        "host\x00null",
        "host\nnewline",
    ],
)
def test_rejects_invalid(raw: str) -> None:
    assert normalize_diagnostic_host(raw) is None


def test_strips_whitespace_before_validation() -> None:
    result = normalize_diagnostic_host("  8.8.8.8  ")
    assert result in ("8.8.8.8", None)
