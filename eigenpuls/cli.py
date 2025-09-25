from __future__ import annotations

from .config import DEFAULT_HOST, DEFAULT_PORT

import os
from typing import Optional

import fire
import uvicorn


class CLI:

    def version(self) -> str:
        try:
            from importlib.metadata import version
            return version("eigenpuls")
        except Exception:
            return "0+unknown"


    def serve(self, host: Optional[str] = DEFAULT_HOST, port: Optional[int] = DEFAULT_PORT, config: Optional[str] = None) -> None:
        from .config import AppConfig
        from .api import app

        if config:
            os.environ["EIGENPULS_CONFIG"] = config

        config_model = AppConfig()
        host = host or config_model.host
        port = port or config_model.port

        try:
            uvicorn.run(app, host=host, port=port)
        except KeyboardInterrupt:
            # Graceful shutdown without traceback
            pass


    def install_system_packages(self, config: Optional[str] = None) -> None:
        from .config import AppConfig
        from .service.base import SystemPackageType

        if config:
            os.environ["EIGENPULS_CONFIG"] = config

        cfg = AppConfig()
        pkg_type = SystemPackageType.detect_by_os()

        package_set = set()
        for svc in cfg.services:
            package_set.update(svc.get_system_packages(pkg_type))

        packages = sorted(package_set)
        if not packages:
            print("No additional system packages required.")
            return

        if pkg_type == SystemPackageType.APT:
            print("APT packages required:")
            for pkg in packages:
                print(f"  - {pkg}")
            print(f"Install command: sudo apt-get update && sudo apt-get install -y {' '.join(packages)}")
        else:
            print(f"Packages required for {pkg_type}:")
            for pkg in packages:
                print(f"  - {pkg}")
            print(f"Install command: sudo {pkg_type.value} install -y {' '.join(packages)}")


    def packages(self, config: Optional[str] = None, type: Optional[str] = None, sep: str = " ") -> None:
        """Print only the package names for use in Dockerfile RUN steps.
        Args:
            config: path to YAML config
            type: package manager type (e.g. 'apt'); auto-detect if omitted
            sep: separator between package names (default: space)
        """
        from .config import AppConfig
        from .service.base import SystemPackageType

        if config:
            os.environ["EIGENPULS_CONFIG"] = config

        if type is None:
            pkg_type = SystemPackageType.detect_by_os()
        else:
            type_lower = type.lower()
            if type_lower == "apt":
                pkg_type = SystemPackageType.APT
            else:
                raise ValueError(f"Unsupported package type: {type}")

        cfg = AppConfig()
        package_set = set()
        for svc in cfg.services:
            package_set.update(svc.get_system_packages(pkg_type))

        # Print only names, no extra text
        print(sep.join(sorted(package_set)))


    def dockerfile(self) -> str:
        from .config import AppConfig
        
        cfg = AppConfig()    
        print(cfg.dockerfile())
        return cfg.dockerfile()


def main():
    import os
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)



