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

    def run(self) -> ServiceStatus:
        # Prefer rabbitmq-diagnostics; fallback to rabbitmqctl
        missing = self.binaries_missing(["rabbitmq-diagnostics"])  # returns list
        if missing:
            if self.binaries_missing(["rabbitmqctl"]):
                pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
                return ServiceStatus(
                    status=ServiceHealth.ERROR,
                    details=f"Missing rabbitmq client binaries. Install packages: {pkgs}",
                )
            cmd = "rabbitmqctl status"
            code, out, err = self.run_shell(cmd)
            if code == 0:
                return ServiceStatus(status=ServiceHealth.OK, details="rabbitmqctl status ok")
            return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

        # Diagnostics available
        base = (
            "rabbitmq-diagnostics -q check_running && "
            "rabbitmq-diagnostics -q check_port_listener %port% && "
            "rabbitmq-diagnostics -q check_local_alarms"
        )
        cmd = self.replace_placeholders(base)
        code, out, err = self.run_shell(cmd)
        if code == 0:
            return ServiceStatus(status=ServiceHealth.OK, details="diagnostics ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        return self.replace_placeholders(
            "rabbitmq-diagnostics -q check_running && rabbitmq-diagnostics -q check_port_listener %port% && rabbitmq-diagnostics -q check_local_alarms"
        )

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # rabbitmq-diagnostics is in rabbitmq-server; rabbitmqctl is in rabbitmq-server too
                return ["rabbitmq-server"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.RABBITMQ, RabbitMQService)