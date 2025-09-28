from __future__ import annotations

import asyncio
from threading import Thread, Lock
from typing import Optional

import uvicorn
from fastapi import FastAPI


_app: FastAPI | None = None
_server: uvicorn.Server | None = None
_thread: Thread | None = None
_lock = Lock()
_started: bool = False
_require_worker_ping: bool = False


def _build_app() -> FastAPI:
    app = FastAPI(title="eigenpuls-celery-health")

    @app.get("/health")
    async def health():
        payload = {"status": "ok"}
        broker_ok = False
        worker_ok = True
        workers = 0
        details = ""
        try:
            from celery import current_app as _celery_app  # type: ignore
            # Broker connectivity
            try:
                with _celery_app.connection_for_read():
                    broker_ok = True
            except Exception as e:  # pragma: no cover
                broker_ok = False
                details = str(e)
            # Worker responsiveness (only when required)
            if _require_worker_ping and broker_ok:
                try:
                    replies = _celery_app.control.ping(timeout=1)
                    workers = len(replies or [])
                    worker_ok = workers > 0
                except Exception as e:  # pragma: no cover
                    worker_ok = False
                    details = str(e)
        except Exception:  # Celery not available
            payload = {"status": "error", "details": "celery not available"}
            return payload

        overall_ok = broker_ok and (worker_ok if _require_worker_ping else True)
        payload = {
            "status": "ok" if overall_ok else "error",
            "broker": "ok" if broker_ok else "error",
        }
        if _require_worker_ping:
            payload["workers"] = workers
            payload["worker_ping"] = "ok" if worker_ok else "error"
        if not overall_ok and details:
            payload["details"] = details
        return payload

    return app


def start_health_server(host: Optional[str] = None, port: Optional[int] = None, require_worker_ping: bool = False) -> bool:
    global _app, _server, _thread, _started, _require_worker_ping
    with _lock:
        if _started:
            return False
        _require_worker_ping = bool(require_worker_ping)
        _app = _build_app()
        bind_host = host or "0.0.0.0"
        bind_port = int(port) if port is not None else 8099
        config = uvicorn.Config(app=_app, host=bind_host, port=bind_port, log_level="warning", lifespan="off")
        server = uvicorn.Server(config)
        _server = server

        def _run() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                server.run()
            finally:
                with _lock:
                    global _started
                    _started = False
                try:
                    loop.close()
                except Exception:
                    pass

        t = Thread(target=_run, name="eigenpuls-celery-health", daemon=True)
        t.start()
        _thread = t
        _started = True
        return True


def stop_health_server() -> None:
    global _server, _thread, _started
    with _lock:
        srv = _server
        th = _thread
        _server = None
        _thread = None
        _started = False
    try:
        if srv is not None:
            srv.should_exit = True
    except Exception:
        pass
    try:
        if th is not None:
            th.join(timeout=2)
    except Exception:
        pass


