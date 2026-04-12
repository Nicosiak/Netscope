"""Validate user-supplied hosts for ping, traceroute, iperf, etc."""

from __future__ import annotations

import ipaddress
import re
from typing import Optional

# RFC 1035-ish total length bound
_MAX_HOST_LEN = 253

# Disallow shell metacharacters and argument injection patterns
_BAD_CHARS = frozenset(' \n\r\t;|&$`<>()[]{}"\\')


def normalize_diagnostic_host(raw: str) -> Optional[str]:
    """
    Return a normalized host/IP safe to pass as a single argv token, or ``None``.

    Accepts IPv4, IPv6 (with or without brackets), and simple hostnames
    (letters, digits, hyphen, dots between labels).
    """
    if not raw:
        return None
    s = raw.strip()
    if not s or len(s) > _MAX_HOST_LEN:
        return None

    # Bracketed IPv6 e.g. [::1] — before _BAD_CHARS (brackets are not shell tokens here)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        try:
            ipaddress.IPv6Address(inner)
            return s
        except ValueError:
            return None

    if any(c in s for c in _BAD_CHARS):
        return None

    # Unbracketed IPv6
    if ":" in s:
        try:
            ipaddress.IPv6Address(s)
            return s
        except ValueError:
            return None

    try:
        ipaddress.IPv4Address(s)
        return s
    except ValueError:
        pass

    if s.startswith(".") or s.endswith(".") or ".." in s:
        return None

    _LABEL = r"(?!-)[a-zA-Z0-9-]{1,63}"
    if not re.fullmatch(rf"{_LABEL}(\.{_LABEL})*", s):
        return None
    return s
