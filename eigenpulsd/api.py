from __future__ import annotations

import eigenpuls
from eigenpulsd.config import get_app_config
from eigenpuls.service import Service, ServiceResponse, ServiceListResponse, ServiceWorkerResponse, ServiceStatus, ServiceStatusHealth, ServiceConfig, ServiceMode, ServiceStatusList, ServiceHealthResponse
from datetime import datetime, timezone
import time

from fastapi import FastAPI, HTTPException, Depends, Header, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict
import asyncio
from contextlib import asynccontextmanager
import threading

from eigenpulsd.storage import init_store, get_store, with_store_lock

import logging
logger = logging.getLogger("uvicorn.error")


bearer_scheme = HTTPBearer(auto_error=False)
app_data = get_store()


async def app_startup():
    logger.info("eigenpuls starting up")

    get_app_config(reload=True)
    init_store()

    with with_store_lock():
        if not app_data.get("server_start"):
            app_data["server_start"] = time.time()

    return


async def app_shutdown():
    logger.info("eigenpuls shutting down")
    # keep shared store for warm cache across restarts

    return


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
    try:
        yield
    finally:
        await app_shutdown()


app = FastAPI(title="eigenpuls", lifespan=lifespan, version=eigenpuls.__version__)
app.openapi_extra = {
    "info": {
        "version": eigenpuls.__version__
    }
}


def _store_get_server_start() -> float | None:
    with with_store_lock():
        return app_data.get("server_start")


def _get_uptime_seconds() -> float | None:
    try:
        started = _store_get_server_start()
        if not started:
            return None
        return max(0.0, time.time() - float(started))
    except Exception:
        return None


def _get_expected_apikey() -> str | None:
    try:
        cfg = get_app_config()
        key = getattr(cfg, "apikey", None)
        if key is None:
            return None
        try:
            # SecretStr compatible
            return key.get_secret_value()  # type: ignore[attr-defined]
        except Exception:
            return str(key)
    except Exception:
        return None


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = _get_expected_apikey()
    if not expected:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        scheme, token = authorization.split(" ", 1)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if scheme.lower() != "bearer" or token.strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def require_api_key_doc(creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme)) -> None:
    expected = _get_expected_apikey()
    if not expected:
        return
    if not creds or creds.scheme.lower() != "bearer" or creds.credentials != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _store_get_services() -> Dict[str, Service]:
    """Return a mapping of name -> Service from the shared store."""
    with with_store_lock():
        raw = dict(app_data.get("services", {}) or {})
    services: Dict[str, Service] = {}
    for name, data in raw.items():
        try:
            services[name] = Service.model_validate(data)
        except Exception:
            continue
    return services


def _store_set_services(services: Dict[str, Service]) -> None:
    with with_store_lock():
        app_data["services"] = {name: svc.model_dump() for name, svc in services.items()}


def _store_get_service(name: str) -> Service | None:
    with with_store_lock():
        data = (app_data.get("services", {}) or {}).get(name)
    if not data:
        return None
    try:
        return Service.model_validate(data)
    except Exception:
        return None


def _compute_service_response(svc: Service) -> Dict:
    return ServiceResponse.from_service(svc).model_dump()


def _store_get_responses() -> Dict[str, Dict]:
    with with_store_lock():
        return dict(app_data.get("responses", {}) or {})


def _store_get_response(name: str) -> Dict | None:
    with with_store_lock():
        docs = app_data.get("responses", {}) or {}
        return docs.get(name)


def _store_update_worker(service_name: str, worker_name: str, health: ServiceStatusHealth) -> Service:
    now = datetime.now(timezone.utc)
    with with_store_lock():
        raw = app_data.get("services", {})
        data = raw.get(service_name)
        if data:
            try:
                svc = Service.model_validate(data)
            except Exception:
                svc = Service(name=service_name)
        else:
            svc = Service(name=service_name)
        # upsert into list by worker_name
        status = svc.workers.find_by_name(worker_name) if svc.workers else None
        if status is None:
            status = ServiceStatus(worker_name=worker_name)
        status.health = health
        status.checked_at = now
        if not svc.workers:
            svc.workers = ServiceStatusList(root=[status])
        else:
            svc.workers.upsert(status)
        # Set first_running_at when first worker reaches RUNNING
        if health.mode == ServiceMode.RUNNING and not svc.first_running_at:
            svc.first_running_at = now
        # Clear first_running_at if no workers are RUNNING anymore
        any_running = any(w.health.mode == ServiceMode.RUNNING for w in (svc.workers.root if svc.workers else []))
        if not any_running:
            svc.first_running_at = None
        raw[service_name] = svc.model_dump()
        app_data["services"] = raw
        # cache response doc for fast GETs
        app_data.setdefault("responses", {})
        app_data["responses"][service_name] = _compute_service_response(svc)
        return svc


def _store_update_config(service_name: str, config: ServiceConfig) -> Service:
    with with_store_lock():
        raw = app_data.get("services", {})
        data = raw.get(service_name)
        if data:
            try:
                svc = Service.model_validate(data)  # type: ignore[attr-defined]
            except Exception:
                # If existing data is invalid, recreate service
                svc = Service(name=service_name)
        else:
            # Create new service when not found
            svc = Service(name=service_name)
        svc.config = config
        raw[service_name] = svc.model_dump()
        app_data["services"] = raw
        # cache response doc for fast GETs
        app_data.setdefault("responses", {})
        app_data["responses"][service_name] = _compute_service_response(svc)
        return svc


@app.get("/health")
async def health() -> ServiceHealthResponse:
    # Own health check, api is healthy, return uptime of local process
    uptime = _get_uptime_seconds()
    return ServiceHealthResponse(ok=True, uptime_seconds=uptime)


@app.get("/health/service")
async def health_service_list() -> ServiceListResponse:
    # Try cached responses first
    docs = _store_get_responses()
    if docs:
        uptime = _get_uptime_seconds()
        models = []
        for _name, doc in docs.items():
            try:
                sr = ServiceResponse.model_validate(doc)
                if uptime is not None:
                    sr.server_uptime_seconds = uptime
                models.append(sr)
            except Exception:
                continue
        return ServiceListResponse(services=models)
    # Fallback to computing
    services = list(_store_get_services().values())
    resp = ServiceListResponse.from_services(services)
    uptime = _get_uptime_seconds()
    if uptime is not None:
        for s in resp.services:
            s.server_uptime_seconds = uptime
    return resp


@app.get("/health/service/{service_name}")
async def health_service_get(service_name: str) -> ServiceResponse:
    # Try cached response first
    doc = _store_get_response(service_name)
    if doc:
        try:
            resp = ServiceResponse.model_validate(doc)
            uptime = _get_uptime_seconds()
            if uptime is not None:
                resp.server_uptime_seconds = uptime
            return resp
        except Exception:
            pass
    svc = _store_get_service(service_name)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    resp = ServiceResponse.from_service(svc)
    uptime = _get_uptime_seconds()
    if uptime is not None:
        resp.server_uptime_seconds = uptime
    return resp


@app.post("/health/service/{service_name}/config")
async def health_service_config_update(service_name: str, config: ServiceConfig, _auth: None = Depends(require_api_key_doc)) -> ServiceResponse:
    svc = _store_update_config(service_name, config)
    resp = ServiceResponse.from_service(svc)
    uptime = _get_uptime_seconds()
    if uptime is not None:
        resp.server_uptime_seconds = uptime
    return resp


@app.get("/health/service/{service_name}/worker/{worker_name}")
async def health_service_worker_get(service_name: str, worker_name: str) -> ServiceWorkerResponse:
    svc = _store_get_service(service_name)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    if not svc.workers or not svc.workers.find_by_name(worker_name):
        raise HTTPException(status_code=404, detail="Worker not found")
    st = svc.workers.find_by_name(worker_name)
    return ServiceWorkerResponse.from_worker(worker_name, st)


@app.post("/health/service/{service_name}/worker/{worker_name}")
async def health_service_worker_update(service_name: str, worker_name: str, health: ServiceStatusHealth, _auth: None = Depends(require_api_key_doc)) -> ServiceWorkerResponse:
    svc = _store_update_worker(service_name, worker_name, health)
    if not svc:
        raise HTTPException(status_code=404, detail="Service failed to update")
    st = svc.workers.find_by_name(worker_name) if svc.workers else None
    if not st:
        raise HTTPException(status_code=404, detail="Worker failed to update")
    return ServiceWorkerResponse.from_worker(worker_name, st)

