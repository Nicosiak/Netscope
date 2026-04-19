"""Unit tests for dns_collector (mocked subprocess)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from collectors import dns_collector as dc
from collectors.dns_collector import compare_servers, dig_query

_FAKE_DIG_FULL = """
; <<>> DiG 9.10.6 <<>> google.com A +noall +answer +stats
;; global options: +cmd
; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1
;; flags: qr rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 1
;; ANSWER SECTION:
google.com.     300 IN  A   142.250.80.46
;; Query time: 14 msec
;; SERVER: 192.168.1.1#53(192.168.1.1)
"""


def test_dig_query_parses_query_time_and_server() -> None:
    with patch("collectors.dns_collector.run_text") as run_text:
        run_text.return_value = MagicMock(stdout=_FAKE_DIG_FULL, stderr="")
        out = dig_query("google.com")
        assert out["query_time_ms"] == 14
        assert out["server"] is not None
        assert "192.168.1.1" in out["server"]
        assert out["answer_count"] == 1
        assert len(out["answers"]) == 1
        assert out["answers"][0]["type"] == "A"
        assert out["answers"][0]["data"] == "142.250.80.46"


def test_dig_query_aaaa_uses_type_in_argv() -> None:
    captured: list[list[str]] = []

    def capture(args, timeout):  # type: ignore[no-untyped-def]
        captured.append(list(args))

        class P:
            stdout = _FAKE_DIG_FULL.replace(" A ", " AAAA ").replace("IN  A", "IN  AAAA")
            stderr = ""

        return P()

    with patch("collectors.dns_collector.run_text", side_effect=capture):
        dig_query("google.com", record_type="AAAA")
    assert captured
    assert "AAAA" in captured[0]


def test_dig_query_handles_subprocess_error() -> None:
    with patch("collectors.dns_collector.run_text", side_effect=OSError("boom")):
        out = dig_query("example.com")
        assert out["query_time_ms"] is None
        assert "boom" in out["raw"]


def test_compare_servers_preserves_order_with_executor() -> None:
    n = [0]

    def fake_run_text(args, timeout):  # type: ignore[no-untyped-def]
        n[0] += 1

        class P:
            stdout = _FAKE_DIG_FULL.replace("14 msec", f"{10 + n[0]} msec")
            stderr = ""

        return P()

    with patch("collectors.dns_collector.run_text", side_effect=fake_run_text):
        rows = compare_servers("google.com", "A")
    assert len(rows) == 4
    assert [r["label"] for r in rows] == [
        "System DNS",
        "Google (8.8.8.8)",
        "Cloudflare (1.1.1.1)",
        "Quad9 (9.9.9.9)",
    ]


def test_dig_not_on_path() -> None:
    with patch.object(dc, "dig_available", return_value=False):
        out = dig_query("google.com")
        assert "dig not found" in (out.get("raw") or "").lower()
