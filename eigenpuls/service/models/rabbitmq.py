from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List


class RabbitMQService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.RABBITMQ, **data)

    async def run(self) -> ServiceStatus:
        # Prefer rabbitmq-diagnostics; fallback to rabbitmqctl
        missing = self.binaries_missing(["rabbitmq-diagnostics"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing rabbitmq client binaries. Install packages: {pkgs}",
            )

        cmd = self.build_command()
        code, out, err = await self.run_shell_async(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="diagnostics ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        cookie_arg = ""
        try:
            cookie_value = None
            if self.cookie:
                cookie_value = self.cookie.get_secret_value() if hasattr(self.cookie, "get_secret_value") else str(self.cookie)
            if cookie_value:
                _val = "'" + cookie_value.replace("'", "'\"'\"'") + "'"
                cookie_arg = f"--erlang-cookie {_val} "
        except Exception:
            cookie_arg = ""

        return (
            f"rabbitmq-diagnostics {cookie_arg} -n rabbit@{self.host} -q check_running && "
            f"rabbitmq-diagnostics {cookie_arg} -n rabbit@{self.host} -q check_port_listener {self.port} && "
        )

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # rabbitmq-diagnostics is in rabbitmq-server; rabbitmqctl is in rabbitmq-server too
                return ["rabbitmq-server"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.RABBITMQ, RabbitMQService)