"""nmap collector — argv shape, availability, mocked subprocess, XML parse."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from collectors import nmap_collector as nm

_FIXTURE_XML = (Path(__file__).resolve().parent / "fixtures" / "nmap_sample.xml").read_text(
    encoding="utf-8"
)
_FIXTURE_OPEN_ONLY = (
    Path(__file__).resolve().parent / "fixtures" / "nmap_open_no_service.xml"
).read_text(encoding="utf-8")


def test_preset_ids_cover_expected_keys() -> None:
    keys = set(nm.preset_ids())
    assert keys == {
        "quick",
        "services",
        "safe_scripts",
        "vuln",
        "discovery",
        "ssl",
        "udp_top",
    }


def test_parse_nmap_xml_opens_ports() -> None:
    scan = nm._parse_nmap_xml(_FIXTURE_XML)
    assert "parse_error" not in scan
    assert len(scan["ports"]) == 1
    assert scan["ports"][0]["port"] == "22"
    assert scan["ports"][0]["service"] == "ssh"
    assert "OpenSSH" in scan["ports"][0]["product"]


def test_parse_nmap_xml_open_port_without_service_element() -> None:
    scan = nm._parse_nmap_xml(_FIXTURE_OPEN_ONLY)
    assert len(scan["ports"]) == 1
    assert scan["ports"][0]["port"] == "49152"
    assert scan["ports"][0]["service"] == "unknown"
    assert "syn-ack" in scan["ports"][0]["product"].lower()


def test_stderr_or_summary_when_empty() -> None:
    scan = nm._parse_nmap_xml(_FIXTURE_OPEN_ONLY)
    text = nm._stderr_or_summary("", scan, "127.0.0.1")
    assert "49152" in text
    assert "127.0.0.1" in text
    assert "Open ports" in text or "open" in text.lower()


def test_run_nmap_unknown_preset() -> None:
    with patch.object(nm, "nmap_available", return_value=True):
        r = nm.run_nmap("127.0.0.1", "not-a-preset")
    assert r["ok"] is False
    assert r["available"] is True
    assert "Unknown preset" in (r.get("error") or "")


def test_run_nmap_not_installed() -> None:
    with patch.object(nm, "nmap_available", return_value=False):
        r = nm.run_nmap("127.0.0.1", "quick")
    assert r["ok"] is False
    assert r["available"] is False
    assert "not found" in (r.get("error") or "").lower()


def test_run_nmap_quick_invokes_nmap_with_host_last() -> None:
    captured: list[list[str]] = []

    def fake_run_text(args, timeout):  # type: ignore[no-untyped-def]
        captured.append(list(args))

        class P:
            returncode = 0
            stdout = _FIXTURE_XML
            stderr = "Nmap scan report for 192.168.1.1\n"

        return P()

    with patch.object(nm, "nmap_available", return_value=True):
        with patch.object(nm, "run_text", side_effect=fake_run_text):
            r = nm.run_nmap("192.168.1.1", "quick")
    assert r["ok"] is True
    assert r["exit_code"] == 0
    assert r["duration_ms"] is not None
    assert isinstance(r["argv"], list)
    assert captured
    argv = captured[0]
    assert argv[0] == "nmap"
    assert argv[-1] == "192.168.1.1"
    assert "-oX" in argv
    i = argv.index("-oX")
    assert argv[i + 1] == "-"
    assert "-sT" in argv
    assert "--top-ports" in argv
    assert r["scan"] is not None
    assert len(r["scan"]["ports"]) == 1
    assert "Nmap scan report" in (r.get("raw") or "")


def test_run_nmap_synthetic_raw_when_stderr_empty() -> None:
    captured: list[list[str]] = []

    def fake_run_text(args, timeout):  # type: ignore[no-untyped-def]
        captured.append(list(args))

        class P:
            returncode = 0
            stdout = _FIXTURE_OPEN_ONLY
            stderr = ""

        return P()

    with patch.object(nm, "nmap_available", return_value=True):
        with patch.object(nm, "run_text", side_effect=fake_run_text):
            r = nm.run_nmap("127.0.0.1", "quick")
    assert r["ok"] is True
    assert "49152" in (r.get("raw") or "")
    assert "summary" in (r.get("raw") or "").lower() or "Open ports" in (r.get("raw") or "")


def test_run_nmap_timeout() -> None:
    import subprocess

    with patch.object(nm, "nmap_available", return_value=True):
        with patch.object(nm, "run_text", side_effect=subprocess.TimeoutExpired("nmap", 1)):
            r = nm.run_nmap("127.0.0.1", "quick")
    assert r["ok"] is False
    assert r["exit_code"] == -1
    assert "timeout" in (r.get("error") or "").lower()
    assert r.get("duration_ms") is not None
    assert r.get("argv")


def test_run_nmap_ssl_preset_argv() -> None:
    captured: list[list[str]] = []

    def fake_run_text(args, timeout):  # type: ignore[no-untyped-def]
        captured.append(list(args))

        class P:
            returncode = 0
            stdout = "<nmaprun></nmaprun>"
            stderr = ""

        return P()

    with patch.object(nm, "nmap_available", return_value=True):
        with patch.object(nm, "run_text", side_effect=fake_run_text):
            r = nm.run_nmap("127.0.0.1", "ssl")
    assert r["ok"] is True
    assert "-p" in captured[0]
    assert "443" in captured[0]
    assert "ssl-cert" in "".join(captured[0])


def test_run_nmap_busy_when_locked() -> None:
    import threading

    hold = threading.Event()
    done = threading.Event()
    captured: list[int] = []

    def slow_run_text(args, timeout):  # type: ignore[no-untyped-def]
        captured.append(1)
        hold.wait(timeout=5.0)

        class P:
            returncode = 0
            stdout = "<nmaprun></nmaprun>"
            stderr = ""

        return P()

    def run_slow() -> None:
        try:
            with patch.object(nm, "nmap_available", return_value=True):
                with patch.object(nm, "run_text", side_effect=slow_run_text):
                    nm.run_nmap("127.0.0.1", "quick")
        finally:
            done.set()

    t = threading.Thread(target=run_slow)
    t.start()
    try:
        import time

        deadline = time.monotonic() + 2.0
        while len(captured) < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        r2 = nm.run_nmap("127.0.0.1", "quick")
        assert r2["ok"] is False
        assert "already running" in (r2.get("error") or "").lower()
    finally:
        hold.set()
        done.wait(timeout=5.0)
        t.join(timeout=5.0)
