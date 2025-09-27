from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List
import urllib.request
import urllib.error
import asyncio


class HTTPService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.HTTP, **data)

    async def run(self) -> ServiceStatus:
        # Use Python stdlib HTTP client only; no external binaries
        url = self.replace_placeholders("http://%host%:%port%/")
        try:
            loop = asyncio.get_running_loop()
            timeout_seconds = self.timeout or 10
            def _fetch() -> int:
                with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
                    return resp.getcode() or 0
            status_code = await loop.run_in_executor(None, _fetch)
            if status_code < 500:
                return ServiceStatus(status=ServiceHealth.OK, details=f"http status {status_code}")
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"http status {status_code}")
        except urllib.error.HTTPError as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"http error {e.code}")
        except Exception as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=str(e))

    def build_command(self) -> str:
        return self.replace_placeholders("GET http://%host%:%port%/")

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        # No external packages required for Python stdlib HTTP
        match package_type:
            case SystemPackageType.APT:
                return []
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.HTTP, HTTPService)

