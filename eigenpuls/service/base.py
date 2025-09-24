from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Tuple
from datetime import datetime, timezone
import os
import shutil
import subprocess

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
    REDIS = "redis"
    POSTGRES = "postgres"
    RABBITMQ = "rabbitmq"


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
    def run(self) -> ServiceStatus:
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