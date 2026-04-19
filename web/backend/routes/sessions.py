"""Customer session routes."""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter

from core.session import TAGS, Session
from core.session_summary import summarize_snapshots
from core.storage import storage as _storage
from web.backend.models import SessionCreateBody, SessionPatchBody
from web.backend.state import session as _session_state

router = APIRouter()


def _session_to_dict(s: Session) -> Dict[str, Any]:
    return {
        "id": s.id,
        "customer_name": s.customer_name,
        "customer_address": s.customer_address,
        "notes": s.notes,
        "tags": s.tags,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "is_active": s.is_active,
        "duration_s": round(s.duration_s, 1),
    }


@router.post("/api/sessions")
async def create_session(body: SessionCreateBody) -> Dict[str, Any]:
    s = Session(
        customer_name=body.customer_name.strip(),
        customer_address=body.customer_address.strip(),
        notes=body.notes.strip(),
    )
    _storage.save_session(s)
    _session_state.set(s.id)
    return {"session": _session_to_dict(s)}


@router.get("/api/sessions")
async def list_sessions() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        if not _storage._conn:
            return {"sessions": []}
        cur = _storage._conn.execute(
            "SELECT s.id, s.customer_name, s.customer_address, s.notes, s.tags, "
            "s.started_at, s.ended_at, COUNT(sn.id) AS snapshot_count "
            "FROM sessions s "
            "LEFT JOIN snapshots sn ON sn.session_id = s.id AND sn.kind = 'stability' "
            "GROUP BY s.id ORDER BY s.started_at DESC LIMIT 100"
        )
        rows = []
        for r in cur.fetchall():
            s = Session.from_dict({
                "id": r[0], "customer_name": r[1], "customer_address": r[2],
                "notes": r[3], "tags": r[4], "started_at": r[5], "ended_at": r[6],
            })
            d = _session_to_dict(s)
            d["snapshot_count"] = r[7]
            rows.append(d)
        return {"sessions": rows}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.get("/api/sessions/active")
async def get_active_session() -> Dict[str, Any]:
    sid = _session_state.get()
    if not sid:
        return {"session": None}

    def _run() -> Dict[str, Any]:
        if not _storage._conn:
            return {"session": None}
        cur = _storage._conn.execute(
            "SELECT id, customer_name, customer_address, notes, tags, started_at, ended_at "
            "FROM sessions WHERE id = ?", (sid,)
        )
        row = cur.fetchone()
        if not row:
            return {"session": None}
        keys = ["id", "customer_name", "customer_address", "notes", "tags", "started_at", "ended_at"]
        s = Session.from_dict(dict(zip(keys, row)))
        return {"session": _session_to_dict(s)}

    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.post("/api/sessions/{session_id}/end")
async def end_session(session_id: UUID) -> Dict[str, Any]:
    sid = str(session_id)
    _storage.end_session(sid)
    if _session_state.get() == sid:
        _session_state.set(None)
    return {"ok": True}


@router.patch("/api/sessions/{session_id}")
async def patch_session(session_id: UUID, body: SessionPatchBody) -> Dict[str, Any]:
    sid = str(session_id)
    if body.notes is not None:
        _storage.update_notes(sid, body.notes)
    if body.tags is not None:
        valid = [t for t in body.tags if t in TAGS]
        _storage.update_tags(sid, valid)
    return {"ok": True}


@router.get("/api/sessions/{session_id}/snapshots")
async def get_session_snapshots(session_id: UUID) -> Dict[str, Any]:
    sid = str(session_id)

    def _run() -> Dict[str, Any]:
        stability = _storage.get_snapshots(sid, "stability")
        for s in stability:
            s["kind"] = "stability"
        spikes = _storage.get_snapshots(sid, "spike")
        for s in spikes:
            s["kind"] = "spike"
        merged = sorted(stability + spikes, key=lambda x: x["ts"])
        return {"snapshots": merged}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.get("/api/sessions/{session_id}/summary")
async def get_session_summary(session_id: UUID) -> Dict[str, Any]:
    sid = str(session_id)

    def _run() -> Dict[str, Any]:
        snaps = _storage.get_snapshots(sid, "stability")
        spike_events = _storage.get_snapshots(sid, "spike")
        result = summarize_snapshots(snaps, spike_events)

        sess_row: Dict[str, Any] = {}
        if _storage._conn:
            cur = _storage._conn.execute(
                "SELECT customer_name, customer_address, started_at, ended_at FROM sessions WHERE id=?",
                (sid,),
            )
            row = cur.fetchone()
            if row:
                sess_row = {
                    "customer_name": row[0], "customer_address": row[1],
                    "started_at": row[2], "ended_at": row[3],
                }

        return {**result, **sess_row}

    return await asyncio.get_running_loop().run_in_executor(None, _run)
