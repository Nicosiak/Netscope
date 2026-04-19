"""Pydantic request/response models for the NetScope web backend."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HostBody(BaseModel):
    host: str

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


PingTargetBody = HostBody
DiagHost = HostBody


class DnsCompareBody(BaseModel):
    host: str = "google.com"
    record_type: Literal["A", "AAAA"] = "A"

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


class IperfBody(BaseModel):
    host: str
    direction: Literal["download", "upload"] = "download"

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


class SpeedTestBody(BaseModel):
    """Optional cap on networkQuality wall time (seconds, 20–90). Omitted = full default run."""

    max_seconds: Optional[int] = Field(default=None, ge=20, le=90)


class NmapScanBody(BaseModel):
    """Bounded nmap presets; target must be a host you are allowed to scan."""

    host: str = "127.0.0.1"
    preset: Literal[
        "quick",
        "services",
        "safe_scripts",
        "vuln",
        "discovery",
        "ssl",
        "udp_top",
    ] = "quick"


class SessionCreateBody(BaseModel):
    customer_name: str
    customer_address: str = ""
    notes: str = ""


class SessionPatchBody(BaseModel):
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
