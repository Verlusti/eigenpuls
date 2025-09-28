from __future__ import annotations

from eigenpuls.config import AppConfig
from eigenpuls.service.registry import service_registry
from eigenpuls.service.base import Service, ServiceStatus, ServiceHealth, DEFAULT_TIMEOUT_SECONDS, set_debug_enabled

from fastapi import FastAPI, HTTPException, Query
from typing import Dict, List, Tuple
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager
from threading import Lock

import logging
logger = logging.getLogger("uvicorn.error")


services: Dict[str, Service] = {}
services_lock = Lock()
health_cache: Dict[str, Tuple[HealthItem, float]] = {}
HEALTH_TTL_SUCCESS_SECONDS = 8
HEALTH_TTL_ERROR_SECONDS = 2
_refresh_task: asyncio.Task | None = None
_stop_refresh = asyncio.Event()

async def app_startup():
    logger.info("eigenpuls starting up")
    logger.info(f"Searching for services ...")

    config = AppConfig()
    # Set global debug flag
    try:
        set_debug_enabled(bool(getattr(config, "debug", False)))
    except Exception:
        set_debug_enabled(False)
    # derive TTLs from config interval if not explicitly configured elsewhere
    global HEALTH_TTL_SUCCESS_SECONDS, HEALTH_TTL_ERROR_SECONDS
    if not HEALTH_TTL_SUCCESS_SECONDS or HEALTH_TTL_SUCCESS_SECONDS == 8:
        HEALTH_TTL_SUCCESS_SECONDS = max(1, int(config.interval_seconds))
    if not HEALTH_TTL_ERROR_SECONDS or HEALTH_TTL_ERROR_SECONDS == 2:
        HEALTH_TTL_ERROR_SECONDS = max(1, int(config.interval_seconds // 3))
    with services_lock:
        services.clear()

    for service in config.services:
        service_class = service_registry.get(service.type)
        if not service_class:
            logger.error(f"  - Service class not found for type: {service.type}")
            continue

        service_instance = service_class(service.name)
        service_instance.host = service.host
        service_instance.port = service.port
        service_instance.user = service.user
        service_instance.password = service.password
        service_instance.cookie = getattr(service, "cookie", None)
        # Derive a reasonable default timeout if not provided in config
        if not service_instance.timeout:
            # half of interval, capped by default timeout constant
            derived_timeout = min(DEFAULT_TIMEOUT_SECONDS, max(1, int(config.interval_seconds // 2)))
            service_instance.timeout = derived_timeout

        with services_lock:
            services[service_instance.name] = service_instance

        logger.info(f"  * Found service: {service_instance.name} [{service_instance.type.value}]")

    # start background refresher
    global _refresh_task
    _stop_refresh.clear()
    logger.info("health refresher: starting background task")
    _refresh_task = asyncio.create_task(_background_refresh_loop())
    return


async def app_shutdown():
    logger.info("eigenpuls shutting down")
    with services_lock:
        services.clear()
    # stop background refresher
    global _refresh_task
    if _refresh_task is not None:
        _stop_refresh.set()
        try:
            await asyncio.wait_for(_refresh_task, timeout=2)
        except Exception:
            pass
        _refresh_task = None
    logger.info("health refresher: stopped background task")
    return


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
    try:
        yield
    finally:
        await app_shutdown()


app = FastAPI(title="eigenpuls", lifespan=lifespan)


class HealthItem(BaseModel):
    name: str
    type: str
    status: ServiceStatus


async def _background_refresh_loop() -> None:
    try:
        while not _stop_refresh.is_set():
            try:
                with services_lock:
                    svc_list = list(services.values())
                if not svc_list:
                    try:
                        await asyncio.wait_for(_stop_refresh.wait(), timeout=1)
                    except asyncio.TimeoutError:
                        pass
                    continue
                # run all checks concurrently
                loop = asyncio.get_running_loop()
                start_time = loop.time()
                now = start_time
                results = await asyncio.gather(*(svc.run_with_retries() for svc in svc_list), return_exceptions=True)
                for svc, res in zip(svc_list, results):
                    if isinstance(res, Exception):
                        item = HealthItem(name=svc.name, type=svc.type.value, status=ServiceStatus(status=ServiceHealth.ERROR, details=str(res)))
                    else:
                        item = HealthItem(name=svc.name, type=svc.type.value, status=res)
                    health_cache[svc.name] = (item, now)
                # summarize
                ok_count = 0
                err_count = 0
                failed_details = []
                for svc in svc_list:
                    item, _ts = health_cache.get(svc.name, (None, 0.0))
                    if item is None:
                        continue
                    if item.status.status == ServiceHealth.OK:
                        ok_count += 1
                    else:
                        err_count += 1
                        detail = item.status.details if item.status and item.status.details else ""
                        detail = " ".join(detail.split())
                        if len(detail) > 120:
                            detail = detail[:117] + "..."
                        failed_details.append(f"{svc.name}({detail})")
                duration_ms = int((loop.time() - start_time) * 1000)
                if failed_details:
                    logger.info(f"health refresh: total={len(svc_list)} ok={ok_count} err={err_count} dur_ms={duration_ms} failed={'; '.join(failed_details)}")
                else:
                    logger.info(f"health refresh: total={len(svc_list)} ok={ok_count} err={err_count} dur_ms={duration_ms}")
                # sleep proportionally to TTL to keep cache warm
                try:
                    await asyncio.wait_for(_stop_refresh.wait(), timeout=min(HEALTH_TTL_SUCCESS_SECONDS, 5))
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("health refresher: background cycle failed: %s", e)
                # brief pause to avoid hot loop on repeated errors
                try:
                    await asyncio.wait_for(_stop_refresh.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
    except asyncio.CancelledError:
        return


async def _refresh_services_once(svc_list: List[Service]) -> None:
    if not svc_list:
        return
    now = asyncio.get_event_loop().time()
    results = await asyncio.gather(*(svc.run_with_retries() for svc in svc_list), return_exceptions=True)
    for svc, res in zip(svc_list, results):
        if isinstance(res, Exception):
            item = HealthItem(name=svc.name, type=svc.type.value, status=ServiceStatus(status=ServiceHealth.ERROR, details=str(res)))
        else:
            item = HealthItem(name=svc.name, type=svc.type.value, status=res)
        health_cache[svc.name] = (item, now)


@app.get("/health")
async def health(refresh: bool = Query(False)) -> Dict[str, HealthItem]:
    # This is my own health check, not the health check of the services
    with services_lock:
        svc_list = list(services.values())
    # Only return cached data for speed. Optionally schedule refresh in background.
    now = asyncio.get_event_loop().time()
    response: Dict[str, HealthItem] = {}
    to_refresh: List[Service] = []
    for svc in svc_list:
        cached = health_cache.get(svc.name)
        if cached:
            item, ts = cached
            response[svc.name] = item
            if refresh:
                ttl = HEALTH_TTL_SUCCESS_SECONDS if item.status.status == ServiceHealth.OK else HEALTH_TTL_ERROR_SECONDS
                if now - ts > ttl:
                    to_refresh.append(svc)
        else:
            # No cache yet: return PENDING and optionally refresh
            response[svc.name] = HealthItem(name=svc.name, type=svc.type.value, status=ServiceStatus(status=ServiceHealth.PENDING, details="no cached result"))
            if refresh:
                to_refresh.append(svc)

    if refresh and to_refresh:
        asyncio.create_task(_refresh_services_once(to_refresh))
    return response


@app.get("/health/{service_name}")
async def health_service(service_name: str, refresh: bool = Query(False)) -> HealthItem:
    with services_lock:
        service = services.get(service_name)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        now = asyncio.get_event_loop().time()
        cached = health_cache.get(service.name)
        if cached:
            item, ts = cached
            if refresh:
                ttl = HEALTH_TTL_SUCCESS_SECONDS if item.status.status == ServiceHealth.OK else HEALTH_TTL_ERROR_SECONDS
                if now - ts > ttl:
                    asyncio.create_task(_refresh_services_once([service]))
            return item
        # No cache yet
        pending = HealthItem(name=service.name, type=service.type.value, status=ServiceStatus(status=ServiceHealth.PENDING, details="no cached result"))
        if refresh:
            asyncio.create_task(_refresh_services_once([service]))
        return pending