"""Network info and interfaces routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/network/info")
async def network_info() -> Any:
    from collectors import network_info_collector
    return await asyncio.get_running_loop().run_in_executor(None, network_info_collector.fetch)


@router.get("/api/interfaces")
async def get_interfaces() -> Any:
    def _run() -> Any:
        from collectors import interface_collector
        return interface_collector.snapshot()
    return await asyncio.get_running_loop().run_in_executor(None, _run)
