from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List


class RedisService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.REDIS, **data)

    def run(self) -> ServiceStatus:
        # Prefer redis-cli ping
        missing = self.binaries_missing(["redis-cli"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing redis client binaries. Install packages: {pkgs}",
            )

        # redis-cli available; use ping with optional auth
        auth_fragment = ""
        if self.password:
            auth_fragment = f"-a {self.password} "
        base = f"redis-cli -h %host% -p %port% {auth_fragment}PING"
        cmd = self.replace_placeholders(base)
        code, out, err = self.run_shell(cmd)
        if code == 0 and out.strip().upper() == "PONG":
            return ServiceStatus(status=ServiceHealth.OK, details="redis ping ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        auth_fragment = ""
        if self.password:
            auth_fragment = f"-a {self.password} "
        return self.replace_placeholders(f"redis-cli -h %host% -p %port% {auth_fragment}PING")

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # redis-cli is provided by redis-tools
                return ["redis-tools"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.REDIS, RedisService)

