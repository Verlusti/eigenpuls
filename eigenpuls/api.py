from __future__ import annotations

from eigenpuls.config import AppConfig
from eigenpuls.service.registry import service_registry

from fastapi import FastAPI
from contextlib import asynccontextmanager

import logging
logger = logging.getLogger("uvicorn.error")


async def app_startup():
    logger.info("eigenpuls starting up")
    logger.info(f"Searching for services ...")

    config = AppConfig()

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
        
        logger.info(f"  * Found service: {service_instance.name} [{service_instance.type.value}]")


    return


async def app_shutdown():
    logger.info("eigenpuls shutting down")
    return

@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
    try:
        yield
    finally:
        await app_shutdown()


app = FastAPI(title="eigenpuls", lifespan=lifespan)


@app.get("/api/v1/health")
async def health():
    return {"services": []}


