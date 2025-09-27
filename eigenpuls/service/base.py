from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Tuple
from datetime import datetime, timezone
import os
import shutil
import subprocess
import asyncio
import contextlib

from pydantic import BaseModel, Field, PrivateAttr

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 10


class SystemPackageType(str, Enum):
    APT = "apt"

    @staticmethod
    def detect_by_os() -> "SystemPackageType":
        if os.path.exists("/usr/bin/apt"):
            return SystemPackageType.APT
        raise ValueError("Unknown operating system")


class KnownServiceType(str, Enum):
    ICMP = "icmp"
    DNS = "dns"
    HTTP = "http"
    REDIS = "redis"
    POSTGRES = "postgres"
    RABBITMQ = "rabbitmq"
    CELERY_WORKER = "celery-worker"
    CELERY_BEAT = "celery-beat"
    CELERY_FLOWER = "celery-flower"


class ServiceHealth(str, Enum):
    PENDING = "pending"
    OK = "ok"
    ERROR = "error"


class ServiceStatus(BaseModel):
    status: ServiceHealth
    details: str
    stacktrace: Optional[str] = None
    retries: int = 0
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_retry_at: Optional[datetime] = None


class Service(BaseModel, ABC):
    name: str
    type: KnownServiceType

    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None

    timeout: Optional[int] = DEFAULT_TIMEOUT_SECONDS
    max_retries: Optional[int] = DEFAULT_MAX_RETRIES

    _status: ServiceStatus = PrivateAttr(default_factory=lambda: ServiceStatus(status=ServiceHealth.PENDING, details="", retries=0))


    @abstractmethod
    async def run(self) -> ServiceStatus:
        pass


    @abstractmethod
    def build_command(self) -> str:
        pass


    @abstractmethod
    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        return []


    def replace_placeholders(self, command: str) -> str:
        cmd = command
        cmd = cmd.replace("%host%", (self.host or ""))
        cmd = cmd.replace("%port%", str(self.port or ""))
        cmd = cmd.replace("%user%", (self.user or ""))
        cmd = cmd.replace("%password%", (self.password or ""))
        return cmd


    def binaries_missing(self, binaries: List[str]) -> List[str]:
        return [b for b in binaries if shutil.which(b) is None]


    def run_shell(self, command: str) -> Tuple[int, str, str]:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout or DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"

    async def run_shell_async(self, command: str) -> Tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timeout_seconds = self.timeout or DEFAULT_TIMEOUT_SECONDS
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                with contextlib.suppress(Exception):
                    proc.kill()
                return 124, "", "timeout"
            return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        except Exception as e:
            return 1, "", str(e)

    async def run_with_retries(self) -> ServiceStatus:
        attempts = int(self.max_retries or 0)
        last_status: ServiceStatus | None = None
        for attempt in range(0, attempts + 1):
            result = await self.run()
            # propagate retry counters
            result.retries = attempt
            if result.status == ServiceHealth.OK:
                return result
            last_status = result
            if attempt < attempts:
                # simple exponential backoff capped to timeout
                backoff = min(2 ** attempt, (self.timeout or DEFAULT_TIMEOUT_SECONDS))
                last_status.last_retry_at = datetime.now(timezone.utc)
                await asyncio.sleep(backoff)
        # on exhaustion
        return last_status or ServiceStatus(status=ServiceHealth.ERROR, details="unknown error")