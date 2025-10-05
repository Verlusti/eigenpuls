from __future__ import annotations

"""Server-side CLI for eigenpuls daemon.

This CLI manages and serves the API within the same process. It requires
server dependencies (extras: server).
"""

from .config import get_app_config
from .api import app

import os
import fire
import uvicorn
from typing import Optional


class CLI:

    def __init__(self):
        """Eigenpuls server CLI entrypoint (server-side)."""
        pass


    def version(self) -> str:
        """Print installed eigenpuls package version (server)."""
        try:
            from importlib.metadata import version
            return version("eigenpuls")
        except Exception:
            return "0+unknown"


    def serve(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """Run the eigenpuls daemon API server."""
        
        from .api import app

        config_model = get_app_config()
        host = host or config_model.host
        port = port or config_model.port

        try:
            uvicorn.run(app, host=host, port=port)
        except KeyboardInterrupt:
            pass


    def list_known_types(self) -> None:
        """List known service types (server-side)."""
        from eigenpuls.service import ServiceKnownType
        print("Known service types:")
        for t in ServiceKnownType:
            print(f"  - {t.value}")


    async def service_list(self) -> None:
        """Return in-process service list from the running daemon (server-side)."""
        from .api import health_service_list
        
        resp = await health_service_list()
        print(resp)

    
    def current_apikey(self, show: bool = False) -> None:
        """Show current API key from daemon config (server-side)."""
        from .api import _get_expected_apikey

        key = _get_expected_apikey() or ""
        if show:
            print(f"Current API key: {key}")
            return
        if not key:
            print("Current API key: (not set)")
            return
        masked = key if len(key) <= 6 else f"{key[:3]}***{key[-2:]}"
        print(f"Current API key: {masked}")


    async def service_config(self, service: str, config: str) -> None:
        """Apply ServiceConfig to a service using in-process API (server-side)."""
        from .api import health_service_config
        resp = await health_service_config(service, config)
        print(resp)


    async def service_worker(self, service: str, worker: str, health: str) -> None:
        """Apply ServiceStatusHealth to a worker using in-process API (server-side)."""
        from .api import health_service_worker
        resp = await health_service_worker(service, worker, health)
        print(resp)


def main():
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)
