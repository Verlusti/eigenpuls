from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List


class PostgresService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.POSTGRES, **data)

    def run(self) -> ServiceStatus:
        # Use pg_isready only; no fallbacks
        missing = self.binaries_missing(["pg_isready"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing postgres client binaries. Install packages: {pkgs}",
            )

        cmd = self.replace_placeholders("pg_isready -h %host% -p %port% -U %user%")
        code, out, err = self.run_shell(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="pg_isready ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        return self.replace_placeholders("pg_isready -h %host% -p %port% -U %user%")

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # pg_isready and psql are part of postgresql-client
                return ["postgresql-client"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.POSTGRES, PostgresService)

