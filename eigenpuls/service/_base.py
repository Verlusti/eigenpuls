from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from statistics import median

from pydantic import BaseModel, Field, ConfigDict, RootModel


DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_INTERVAL_SECONDS = 10


class ServiceKnownType(str, Enum):
    UNKNOWN = "unknown"
    ICMP = "icmp"
    DNS = "dns"
    HTTP = "http"
    REDIS = "redis"
    POSTGRES = "postgres"
    RABBITMQ = "rabbitmq"
    CELERY_WORKER = "celery-worker"
    CELERY_BEAT = "celery-beat"
    CELERY_FLOWER = "celery-flower"


class ServiceMode(str, Enum):
    UNKNOWN = "unknown"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ServiceHealth(str, Enum):
    UNKNOWN = "unknown"
    OK = "ok"
    ERROR = "error"


class ServiceHealthWorkerPolicy(str, Enum):
    """
    Determines how to aggregate health statuses from multiple workers.
    """
    ANY = "any"                 # Return OK if any worker is OK
    ALL = "all"                 # Return OK only if all workers are OK
    MAJORITY = "majority"       # Return OK if majority of workers are OK


class ServiceStatusHealth(BaseModel):
    mode: ServiceMode = ServiceMode.UNKNOWN
    status: ServiceHealth = ServiceHealth.UNKNOWN
    details: str = ""
    stacktrace: Optional[str] = None


class ServiceStatus(BaseModel):
    worker_name: Optional[str] = None
    health: ServiceStatusHealth = Field(default_factory=ServiceStatusHealth)
    retries: int = 0
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_retry_at: Optional[datetime] = None


class ServiceStatusList(RootModel[List[ServiceStatus]]):

    def find_by_name(self, worker_name: str) -> Optional[ServiceStatus]:
        for s in self.root:
            if s.worker_name == worker_name:
                return s
        return None


    def upsert(self, status: ServiceStatus) -> None:
        if not status.worker_name:
            # ignore unnamed workers
            self.root.append(status)
            return
        existing = self.find_by_name(status.worker_name)
        if existing is None:
            self.root.append(status)
        else:
            idx = self.root.index(existing)
            self.root[idx] = status


class ServiceConfig(BaseModel):
    type: ServiceKnownType = ServiceKnownType.UNKNOWN
    policy: ServiceHealthWorkerPolicy = ServiceHealthWorkerPolicy.ALL
    interval: Optional[int] = DEFAULT_INTERVAL_SECONDS
    timeout: Optional[int] = DEFAULT_TIMEOUT_SECONDS
    max_retries: Optional[int] = DEFAULT_MAX_RETRIES


class Service(BaseModel, ABC):
    model_config = ConfigDict(validate_assignment=True)

    name: str
    config: ServiceConfig = Field(default_factory=ServiceConfig)
    workers: ServiceStatusList = Field(default_factory=lambda: ServiceStatusList(root=[]))
    first_running_at: Optional[datetime] = None


    def to_response(self) -> ServiceResponse:
        return ServiceResponse.from_service(self)


class ServiceResponse(Service):    
    timestamp_now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_checked_at: Optional[datetime] = None
    since_last_check: Optional[timedelta] = None
    aggregate_status: ServiceHealth = ServiceHealth.UNKNOWN
    aggregate_mode: ServiceMode = ServiceMode.UNKNOWN
    uptime: Optional[timedelta] = None
    server_uptime_seconds: Optional[float] = None
    

    @classmethod
    def from_service(cls, service: Service) -> ServiceResponse:
        # compute since_last_check from any worker entry if available
        last_checked_at = None
        # aggregate health and mode based on policy
        agg_status = ServiceHealth.UNKNOWN
        agg_mode = ServiceMode.UNKNOWN
        if service.workers and service.workers.root:
            try:
                statuses = [w.health.status for w in service.workers.root]
                modes = [w.health.mode for w in service.workers.root]
                if service.config.policy == ServiceHealthWorkerPolicy.ANY:
                    last_checked_at = max((w.checked_at for w in service.workers.root))
                    agg_status = ServiceHealth.OK if any(s == ServiceHealth.OK for s in statuses) else ServiceHealth.ERROR if any(s == ServiceHealth.ERROR for s in statuses) else ServiceHealth.UNKNOWN
                    # Prefer RUNNING if any, else highest severity by order
                    agg_mode = ServiceMode.RUNNING if any(m == ServiceMode.RUNNING for m in modes) else ServiceMode.STARTING if any(m == ServiceMode.STARTING for m in modes) else ServiceMode.STOPPING if any(m == ServiceMode.STOPPING for m in modes) else ServiceMode.STOPPED if any(m == ServiceMode.STOPPED for m in modes) else ServiceMode.FAILED if any(m == ServiceMode.FAILED for m in modes) else ServiceMode.UNKNOWN
                elif service.config.policy == ServiceHealthWorkerPolicy.ALL:
                    last_checked_at = min((w.checked_at for w in service.workers.root))
                    agg_status = ServiceHealth.OK if all(s == ServiceHealth.OK for s in statuses) else ServiceHealth.ERROR if any(s == ServiceHealth.ERROR for s in statuses) else ServiceHealth.UNKNOWN
                    agg_mode = ServiceMode.RUNNING if all(m == ServiceMode.RUNNING for m in modes) else ServiceMode.STARTING if any(m == ServiceMode.STARTING for m in modes) else ServiceMode.STOPPING if any(m == ServiceMode.STOPPING for m in modes) else ServiceMode.STOPPED if all(m == ServiceMode.STOPPED for m in modes) else ServiceMode.FAILED if any(m == ServiceMode.FAILED for m in modes) else ServiceMode.UNKNOWN
                elif service.config.policy == ServiceHealthWorkerPolicy.MAJORITY:
                    last_checked_at = median((w.checked_at for w in service.workers.root))
                    # majority by count
                    ok_count = sum(1 for s in statuses if s == ServiceHealth.OK)
                    err_count = sum(1 for s in statuses if s == ServiceHealth.ERROR)
                    total = len(statuses)
                    agg_status = ServiceHealth.OK if ok_count > total / 2 else ServiceHealth.ERROR if err_count > total / 2 else ServiceHealth.UNKNOWN
                    # mode majority vote (fallback to most frequent)
                    from collections import Counter
                    agg_mode = Counter(modes).most_common(1)[0][0]
                else:
                    raise ValueError(f"Invalid policy: {service.config.policy}")

            except Exception:
                last_checked_at = None
                agg_status = ServiceHealth.UNKNOWN
                agg_mode = ServiceMode.UNKNOWN
        # compute service uptime from first_running_at only
        uptime: Optional[timedelta] = None
        if service.first_running_at:
            try:
                uptime = datetime.now(timezone.utc) - service.first_running_at
            except Exception:
                uptime = None

        return cls(
            name=service.name,
            config=service.config,
            workers=service.workers,
            timestamp_now=datetime.now(timezone.utc),
            since_last_check=(datetime.now(timezone.utc) - last_checked_at) if last_checked_at else None,
            last_checked_at=last_checked_at,
            aggregate_status=agg_status,
            aggregate_mode=agg_mode,
            uptime=uptime,
        )


class ServiceListResponse(BaseModel):
    services: List[ServiceResponse]


    @classmethod
    def from_services(cls, services: List[Service]) -> ServiceListResponse:
        return cls(services=[service.to_response() for service in services])


class ServiceWorkerResponse(BaseModel):
    worker: str
    status: ServiceStatus = Field(default_factory=ServiceStatus)


    @classmethod
    def from_worker(cls, worker: str, status: ServiceStatus) -> ServiceWorkerResponse:
        return cls(worker=worker, status=status)