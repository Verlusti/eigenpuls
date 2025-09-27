from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List
import asyncio
import urllib.request
import urllib.error


class CeleryWorkerService(Service):
    
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_WORKER, **data)


    async def run(self) -> ServiceStatus:
        # Check for celery worker process. Users often run as `celery -A app worker`.
        missing = self.binaries_missing(["pgrep"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing required binaries. Install packages: {pkgs}",
            )

        cmd = "pgrep -f 'celery.*worker' >/dev/null"
        code, out, err = await self.run_shell_async(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="celery worker running")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")


    def build_command(self) -> str:
        return "pgrep -f 'celery.*worker' >/dev/null"


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                return ["procps"]  # provides pgrep
        raise ValueError(f"Unsupported package type: {package_type}")


class CeleryBeatService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_BEAT, **data)


    async def run(self) -> ServiceStatus:
        missing = self.binaries_missing(["pgrep"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing required binaries. Install packages: {pkgs}",
            )

        cmd = "pgrep -f 'celery.*beat' >/dev/null"
        code, out, err = await self.run_shell_async(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="celery beat running")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")


    def build_command(self) -> str:
        return "pgrep -f 'celery.*beat' >/dev/null"


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                return ["procps"]
        raise ValueError(f"Unsupported package type: {package_type}")


class CeleryFlowerService(Service):

    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_FLOWER, **data)


    async def run(self) -> ServiceStatus:
        # Use Python stdlib HTTP client to query Flower API
        url = self.replace_placeholders("http://%host%:%port%/api/workers")
        try:
            loop = asyncio.get_running_loop()
            timeout_seconds = self.timeout or 10
            def _fetch() -> int:
                with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
                    return resp.getcode() or 0
            status_code = await loop.run_in_executor(None, _fetch)
            if status_code < 500:
                return ServiceStatus(status=ServiceHealth.OK, details="flower http ok")
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"flower http {status_code}")
        except urllib.error.HTTPError as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"flower http {e.code}")
        except Exception as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=str(e))


    def build_command(self) -> str:
        return self.replace_placeholders("GET http://%host%:%port%/api/workers")


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        # No external packages required when using Python stdlib HTTP
        match package_type:
            case SystemPackageType.APT:
                return []
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.CELERY_WORKER, CeleryWorkerService)
service_registry.register(KnownServiceType.CELERY_BEAT, CeleryBeatService)
service_registry.register(KnownServiceType.CELERY_FLOWER, CeleryFlowerService)
