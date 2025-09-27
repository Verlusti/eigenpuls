from .registry import service_registry
from .base import KnownServiceType, Service, SystemPackageType, ServiceStatus, ServiceHealth
from .models.rabbitmq import RabbitMQService
from .models.postgres import PostgresService
from .models.redis import RedisService
from .models.celery import CeleryWorkerService, CeleryBeatService, CeleryFlowerService
from .models.dns import DNSService
from .models.http import HTTPService

from typing import Dict, Type


Implementations: Dict[KnownServiceType, Type[Service]] = {
    KnownServiceType.RABBITMQ: RabbitMQService,
    KnownServiceType.POSTGRES: PostgresService,
    KnownServiceType.REDIS: RedisService,
    KnownServiceType.CELERY_WORKER: CeleryWorkerService,
    KnownServiceType.CELERY_BEAT: CeleryBeatService,
    KnownServiceType.CELERY_FLOWER: CeleryFlowerService,
    KnownServiceType.DNS: DNSService,
    KnownServiceType.HTTP: HTTPService,
}


__all__ = ["service_registry", "KnownServiceType", "Service", "SystemPackageType", "ServiceStatus", "ServiceHealth", "Implementations"]