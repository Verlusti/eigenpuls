from __future__ import annotations

from eigenpuls.config import AppConfig
from eigenpuls.service.registry import service_registry
from eigenpuls.service.base import Service, ServiceStatus, ServiceHealth, DEFAULT_TIMEOUT_SECONDS, set_debug_enabled

from fastapi import FastAPI, HTTPException, Query
from typing import Dict, List, Tuple
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager

import logging
logger = logging.getLogger("uvicorn.error")


services: Dict[str, Service] = {}
services_lock = asyncio.Lock()
health_cache: Dict[str, Tuple[HealthItem, float]] = {}
HEALTH_TTL_SUCCESS_SECONDS = 8
HEALTH_TTL_ERROR_SECONDS = 2
# Per-service orchestration
service_tasks: Dict[str, asyncio.Task] = {}
service_triggers: Dict[str, asyncio.Event] = {}
service_run_locks: Dict[str, asyncio.Lock] = {}
_stop_refresh = asyncio.Event()


def _ttl_ok_seconds(svc: Service) -> int:
    base = int(svc.interval) if svc.interval else HEALTH_TTL_SUCCESS_SECONDS
    return max(1, base)


def _ttl_error_seconds(svc: Service) -> int:
    base = int(svc.interval) if svc.interval else HEALTH_TTL_SUCCESS_SECONDS
    return max(1, int(base // 3) or 1)

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
    async with services_lock:
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
        service_instance.path = getattr(service, "path", None)

        # Ensure interval and timeout defaults per service
        if not service_instance.interval:
            service_instance.interval = max(1, int(config.interval_seconds))
        if not service_instance.timeout:
            # half of service interval, capped by default timeout constant
            derived_timeout = min(DEFAULT_TIMEOUT_SECONDS, max(1, int((service_instance.interval or 1) // 2)))
            service_instance.timeout = derived_timeout

        async with services_lock:
            services[service_instance.name] = service_instance

        logger.info(f"  * Found service: {service_instance.name} [{service_instance.type.value}]")

    # start per-service workers
    _stop_refresh.clear()
    async with services_lock:
        for svc in services.values():
            # initialize trigger and lock
            service_triggers[svc.name] = asyncio.Event()
            service_run_locks[svc.name] = asyncio.Lock()
            # create worker task
            task = asyncio.create_task(_service_worker(svc))
            service_tasks[svc.name] = task
    logger.info("health workers: started per-service background tasks")
    return


async def app_shutdown():
    logger.info("eigenpuls shutting down")
    async with services_lock:
        services.clear()
    # stop per-service workers
    if service_tasks:
        _stop_refresh.set()
        tasks = list(service_tasks.values())
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2)
        except Exception:
            # cancel any stragglers
            for t in tasks:
                if not t.done():
                    t.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)
            except Exception:
                pass
        service_tasks.clear()
        service_triggers.clear()
        service_run_locks.clear()
    logger.info("health workers: stopped per-service background tasks")
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


async def _service_worker(svc: Service) -> None:
    name = svc.name
    try:
        loop = asyncio.get_running_loop()
        trigger = service_triggers.get(name)
        lock = service_run_locks.get(name)
        if trigger is None or lock is None:
            return
        while not _stop_refresh.is_set():
            try:
                # determine remaining time until next refresh based on TTL
                cached = health_cache.get(name)
                if cached:
                    item, ts = cached
                    ttl = _ttl_ok_seconds(svc) if item.status.status == ServiceHealth.OK else _ttl_error_seconds(svc)
                    remaining = max(0.0, ttl - (loop.time() - ts))
                else:
                    remaining = 0.0

                # wait until triggered or TTL expires or stop
                if remaining > 0:
                    wait_tasks = [asyncio.create_task(_stop_refresh.wait()), asyncio.create_task(trigger.wait())]
                    done, pending = await asyncio.wait(wait_tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                    for p in pending:
                        p.cancel()
                    if _stop_refresh.is_set():
                        break
                # clear trigger (if it was set)
                trigger.clear()

                # single-flight per service; avoid busy spin if a run is in progress
                if lock.locked():
                    try:
                        await asyncio.wait_for(_stop_refresh.wait(), timeout=0.1)
                    except asyncio.TimeoutError:
                        pass
                    continue
                async with lock:
                    start = loop.time()
                    try:
                        res = await svc.run_with_retries()
                        item = HealthItem(name=name, type=svc.type.value, status=res)
                    except Exception as e:
                        item = HealthItem(name=name, type=svc.type.value, status=ServiceStatus(status=ServiceHealth.ERROR, details=str(e)))
                    health_cache[name] = (item, loop.time())
                    duration_ms = int((loop.time() - start) * 1000)
                    logger.debug(f"service refresh: {name} dur_ms={duration_ms} status={item.status.status.value}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("service worker '%s' failed: %s", name, e)
                try:
                    await asyncio.wait_for(_stop_refresh.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
    except asyncio.CancelledError:
        return


async def _trigger_services_refresh(svc_list: List[Service]) -> None:
    if not svc_list:
        return
    for svc in svc_list:
        trig = service_triggers.get(svc.name)
        if trig:
            trig.set()


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/health/service")
async def health_service(refresh: bool = Query(False)) -> Dict[str, HealthItem]:
    # This is my own health check, not the health check of the services
    async with services_lock:
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
                ttl = _ttl_ok_seconds(svc) if item.status.status == ServiceHealth.OK else _ttl_error_seconds(svc)
                if now - ts > ttl:
                    to_refresh.append(svc)
        else:
            # No cache yet: return PENDING and optionally refresh
            response[svc.name] = HealthItem(name=svc.name, type=svc.type.value, status=ServiceStatus(status=ServiceHealth.PENDING, details="no cached result"))
            if refresh:
                to_refresh.append(svc)

    if refresh and to_refresh:
        asyncio.create_task(_trigger_services_refresh(to_refresh))
    return response


@app.get("/health/service/{service_name}")
async def health_service(service_name: str, refresh: bool = Query(False)) -> HealthItem:
    async with services_lock:
        service = services.get(service_name)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        now = asyncio.get_event_loop().time()
        cached = health_cache.get(service.name)
        if cached:
            item, ts = cached
            if refresh:
                ttl = _ttl_ok_seconds(service) if item.status.status == ServiceHealth.OK else _ttl_error_seconds(service)
                if now - ts > ttl:
                    asyncio.create_task(_trigger_services_refresh([service]))
            return item
        # No cache yet
        pending = HealthItem(name=service.name, type=service.type.value, status=ServiceStatus(status=ServiceHealth.PENDING, details="no cached result"))
        if refresh:
            asyncio.create_task(_trigger_services_refresh([service]))
        return pending