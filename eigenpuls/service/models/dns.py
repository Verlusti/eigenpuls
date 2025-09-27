from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List


class DNSService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.DNS, **data)

    async def run(self) -> ServiceStatus:
        # Use dig only; no fallbacks
        missing = self.binaries_missing(["dig"])  # returns list
        if missing:
            pkgs = ", ".join(self.get_system_packages(SystemPackageType.detect_by_os()))
            return ServiceStatus(
                status=ServiceHealth.ERROR,
                details=f"Missing DNS client binaries. Install packages: {pkgs}",
            )

        # Resolve A record; success if output not empty
        cmd = self.replace_placeholders("dig +short %host% A")
        code, out, err = await self.run_shell_async(cmd)
        if code == 0 and out.strip():
            return ServiceStatus(status=ServiceHealth.OK, details="dns resolve ok")
        return ServiceStatus(status=ServiceHealth.ERROR, details=err or out or f"exit={code}")

    def build_command(self) -> str:
        return self.replace_placeholders("dig +short %host% A")

    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                # dig is provided by dnsutils
                return ["dnsutils"]
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.DNS, DNSService)

