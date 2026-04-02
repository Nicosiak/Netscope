"""Request macOS Location permission (needed for Wi-Fi scanning on recent macOS)."""

from __future__ import annotations


def request_when_in_use() -> None:
    try:
        from CoreLocation import CLLocationManager  # type: ignore

        manager = CLLocationManager.alloc().init()
        manager.requestWhenInUseAuthorization()
    except Exception:
        # Non-macOS or framework missing — ignore
        pass
