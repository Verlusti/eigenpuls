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
            if self.binaries_missing(["rabbitmqctl"]):
                pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
                return ServiceStatus(
                    status=ServiceHealth.ERROR,
                    details=f"Missing rabbitmq client binaries. Install packages: {pkgs}",
                )
            cookie_arg = ""
            try:
                if self.cookie and self.cookie.get_secret_value():
                    _val = self.cookie.get_secret_value()
                    _val = "'" + _val.replace("'", "'\"'\"'") + "'"
                    cookie_arg = f"--erlang-cookie {_val} "
            except Exception:
                cookie_arg = ""
            cmd = f"rabbitmqctl {cookie_arg}status"
            code, out, err = self.run_shell(cmd)
            if code == 0:
                return ServiceStatus(status=ServiceHealth.OK, details="rabbitmqctl status ok")
            return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

        # Diagnostics available: reuse build_command to avoid duplication
        cmd = self.build_command()
        code, out, err = await self.run_shell_async(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="diagnostics ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        cookie_arg = ""
        try:
            if self.cookie and self.cookie.get_secret_value():
                _val = self.cookie.get_secret_value()
                _val = "'" + _val.replace("'", "'\"'\"'") + "'"
                cookie_arg = f"--erlang-cookie {_val} "
        except Exception:
            cookie_arg = ""
        port_value = str(self.port or "")
        return (
            f"rabbitmq-diagnostics {cookie_arg}-q check_running && "
            f"rabbitmq-diagnostics {cookie_arg}-q check_port_listener {port_value} && "
            f"rabbitmq-diagnostics {cookie_arg}-q check_local_alarms"
        )

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # rabbitmq-diagnostics is in rabbitmq-server; rabbitmqctl is in rabbitmq-server too
                return ["rabbitmq-server"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.RABBITMQ, RabbitMQService)