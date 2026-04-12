"""Unit tests for dns_collector (mocked subprocess)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from collectors.dns_collector import dig_query


def test_dig_query_parses_query_time_and_server() -> None:
    fake_stdout = """
; <<>> DiG 9.10.6 <<>> google.com +stats
;; global options: +cmd
;; Got answer:
;; SERVER: 192.168.1.1#53(192.168.1.1)
;; Query time: 14 msec
"""
    with patch("collectors.dns_collector.run_text") as run_text:
        run_text.return_value = MagicMock(stdout=fake_stdout, stderr="")
        out = dig_query("google.com")
        assert out["query_time_ms"] == 14
        assert out["server"] is not None
        assert "192.168.1.1" in out["server"]


def test_dig_query_handles_subprocess_error() -> None:
    with patch("collectors.dns_collector.run_text", side_effect=OSError("boom")):
        out = dig_query("example.com")
        assert out["query_time_ms"] is None
        assert "boom" in out["raw"]
