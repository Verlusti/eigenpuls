from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List


class CeleryWorkerService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_WORKER, **data)

    def run(self) -> ServiceStatus:
        # Check for celery worker process. Users often run as `celery -A app worker`.
        missing = self.binaries_missing(["pgrep"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing required binaries. Install packages: {pkgs}",
            )

        cmd = "pgrep -f 'celery.*worker' >/dev/null"
        code, out, err = self.run_shell(cmd)
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

    def run(self) -> ServiceStatus:
        missing = self.binaries_missing(["pgrep"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing required binaries. Install packages: {pkgs}",
            )

        cmd = "pgrep -f 'celery.*beat' >/dev/null"
        code, out, err = self.run_shell(cmd)
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

    def run(self) -> ServiceStatus:
        # Prefer checking HTTP endpoint if curl is available; otherwise process check
        if not self.binaries_missing(["curl"]):
            # Expect host/port configured for Flower web
            cmd = self.replace_placeholders("curl -sS -m %port% http://%host%:%port%/api/workers")
            code, out, err = self.run_shell(cmd)
            if code == 0:
                return ServiceStatus(status=ServiceHealth.OK, details="flower http ok")
            return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

        # Fallback to process check if curl missing
        missing = self.binaries_missing(["pgrep"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing required binaries. Install packages: {pkgs}",
            )

        cmd = "pgrep -f 'flower' >/dev/null"
        code, out, err = self.run_shell(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="flower process running")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        return self.replace_placeholders("curl -sS -m %port% http://%host%:%port%/api/workers")

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                return ["curl", "procps"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.CELERY_WORKER, CeleryWorkerService)
service_registry.register(KnownServiceType.CELERY_BEAT, CeleryBeatService)
service_registry.register(KnownServiceType.CELERY_FLOWER, CeleryFlowerService)
