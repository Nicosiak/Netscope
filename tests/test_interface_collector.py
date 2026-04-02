"""Unit tests for interface_collector parsing helpers."""

from __future__ import annotations

from unittest.mock import patch

from collectors import interface_collector as ic


def test_parse_default_gateway() -> None:
    text = """route to: default
destination: default
       gateway: 192.168.1.1
  interface: en0
      flags: UP,GATEWAY,DONE
 recvpipe  sendpipe  ssthresh  rtt,msec    rttvar  hopcount      mtu     expire
       0         0         0         0         0         0      1500         0
"""
    assert ic.parse_default_gateway(text) == "192.168.1.1"


def test_parse_default_gateway_missing() -> None:
    assert ic.parse_default_gateway("no gateway here") is None


def test_wifi_airport_device_parses_listing() -> None:
    listing = """
Hardware Port: Ethernet
Device: en9
Ethernet Address: 11:22:33:44:55:66

Hardware Port: Wi-Fi
Device: en0
Ethernet Address: aa:bb:cc:dd:ee:ff
"""
    with patch.object(ic, "_run", return_value=listing):
        assert ic.wifi_airport_device() == "en0"


def test_wifi_airport_device_airport_label() -> None:
    listing = "Hardware Port: AirPort\nDevice: en1\n"
    with patch.object(ic, "_run", return_value=listing):
        assert ic.wifi_airport_device() == "en1"


def test_wifi_airport_device_not_found() -> None:
    with patch.object(ic, "_run", return_value="Hardware Port: Ethernet\nDevice: en5\n"):
        assert ic.wifi_airport_device() is None
