"""FastAPI app exposing the agent over HTTP and WebSocket."""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .. import __version__
from ..core.config import Settings
from ..core.factory import build_agent
from ..core.types import StreamEvent

STATIC_DIR = Path(__file__).parent / "static"


class RunRequest(BaseModel):
    goal: str
    workspace: str | None = None
    model: str | None = None
    auto_approve: bool = True
    use_memory: bool = True


class PendingApproval:
    def __init__(self) -> None:
        self.events: dict[str, asyncio.Event] = {}
        self.decisions: dict[str, bool] = {}

    async def ask(self, call_id: str) -> bool:
        event = asyncio.Event()
        self.events[call_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            return False
        finally:
            self.events.pop(call_id, None)
        return self.decisions.pop(call_id, False)

    def resolve(self, call_id: str, approved: bool) -> None:
        self.decisions[call_id] = approved
        event = self.events.get(call_id)
        if event:
            event.set()


def _event_payload(event: StreamEvent) -> dict[str, Any]:
    return {"type": event.type, "data": event.data, "timestamp": event.timestamp.isoformat()}


def create_app(settings: Settings | None = None) -> FastAPI:
    base_settings = settings or Settings.load()

    app = FastAPI(title="edarkcode", version=__version__)
    app.state.settings = base_settings

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return HTMLResponse("<h1>edarkcode</h1><p>Web UI assets missing.</p>")
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "provider": base_settings.llm.provider,
            "model": base_settings.llm.model,
            "workspace": str(base_settings.workspace),
            "api_key_configured": bool(base_settings.llm.api_key),
        }

    @app.get("/api/tools")
    async def tools() -> dict[str, Any]:
        from ..core.factory import build_registry

        registry = build_registry(base_settings.workspace)
        return {"tools": [{"name": t.name, "description": t.description} for t in registry._tools.values()]}

    @app.get("/api/memory")
    async def memory() -> dict[str, Any]:
        from ..memory.store import LessonStore, MemoryStore

        mem = MemoryStore(base_settings.memory.path, max_entries=base_settings.memory.max_entries)
        les = LessonStore(base_settings.self_improvement.path, max_entries=base_settings.self_improvement.max_lessons)
        return {
            "memories": [asdict(e) for e in mem.entries()[-100:]],
            "lessons": [asdict(e) for e in les.lessons()],
        }

    @app.post("/api/run")
    async def run_sync(req: RunRequest) -> JSONResponse:
        """Non-streaming run — collects all events and returns the summary."""
        run_settings = _apply_overrides(base_settings, req)
        agent = build_agent(run_settings, approver=None, with_memory=req.use_memory)
        events: list[dict[str, Any]] = []
        result = ""
        try:
            async for event in agent.run(req.goal):
                events.append(_event_payload(event))
                if event.type == "complete":
                    result = (event.data or {}).get("result", "")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            await agent.llm.aclose()
        return JSONResponse({"result": result, "events": events})

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        approvals = PendingApproval()
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "data": {"message": "invalid JSON"}})
                    continue

                mtype = message.get("type")
                if mtype == "approval":
                    approvals.resolve(str(message.get("call_id")), bool(message.get("approved")))
                    continue
                if mtype != "run":
                    await websocket.send_json({"type": "error", "data": {"message": f"unknown type '{mtype}'"}})
                    continue

                req = RunRequest(**{k: v for k, v in message.items() if k != "type"})
                run_settings = _apply_overrides(base_settings, req)

                async def approver(name: str, args: dict, _ws: WebSocket = websocket) -> bool:
                    call_id = f"approve_{name}_{id(args)}"
                    await _ws.send_json(
                        {"type": "approval_request", "data": {"call_id": call_id, "name": name, "arguments": args}}
                    )
                    return await approvals.ask(call_id)

                agent = build_agent(
                    run_settings,
                    approver=None if req.auto_approve else approver,
                    with_memory=req.use_memory,
                )
                try:
                    async for event in agent.run(req.goal):
                        await websocket.send_json(_event_payload(event))
                except Exception as e:  # noqa: BLE001
                    await websocket.send_json({"type": "error", "data": {"message": str(e)}})
                finally:
                    await agent.llm.aclose()
        except WebSocketDisconnect:
            return

    return app


def _apply_overrides(base: Settings, req: RunRequest) -> Settings:
    settings = base.model_copy(deep=True)
    if req.workspace:
        settings.workspace = Path(req.workspace).resolve()
    if req.model:
        settings.llm.model = req.model
    return settings
