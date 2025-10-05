from __future__ import annotations

"""Client-side CLI for eigenpuls.

This CLI talks to a running eigenpuls server over HTTP and has zero
server-side dependencies. It is intended for client/automation usage.
"""

from .config import get_app_config

import os
from typing import Optional

import fire
import uvicorn


CLIENT_SCRIPT_NAME = "eigenpuls-client.sh"


class CLI:

    def __init__(self):
        """Eigenpuls client CLI entrypoint (client-side)."""
        pass


    def version(self) -> str:
        """Print installed eigenpuls package version."""
        try:
            from importlib.metadata import version
            return version("eigenpuls")
        except Exception:
            return "0+unknown"


    def serve(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """Run the eigenpuls API server (requires server extras)."""
        
        from eigenpulsd.api import app

        config_model = get_app_config()
        host = host or config_model.host
        port = port or config_model.port

        try:
            uvicorn.run(app, host=host, port=port)
        except KeyboardInterrupt:
            pass


    def list_known_types(self) -> None:
        """List known service types."""

        from .service import ServiceKnownType

        print("Known service types:")
        for t in ServiceKnownType:
            print(f"  - {t.value}")

    def service_list(self, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """Fetch and print the service list from a running eigenpuls server."""

        from .client import EigenpulsClient
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.list_services()
        print(resp.model_dump())

    
    def current_apikey(self, show: bool = False) -> None:
        """Show current API key (masked by default)."""

        cfg = get_app_config()
        key_obj = getattr(cfg, "apikey", None)
        try:
            key = key_obj.get_secret_value()  # type: ignore[attr-defined]
        except Exception:
            key = str(key_obj or "")
        if show:
            print(f"Current API key: {key}")
            return
        if not key:
            print("Current API key: (not set)")
            return
        masked = key if len(key) <= 6 else f"{key[:3]}***{key[-2:]}"
        print(f"Current API key: {masked}")


    def service_config(self, service: str, config: str, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """POST a ServiceConfig JSON to a running server for the given service."""

        import json as _json
        from .client import EigenpulsClient
        from .service import ServiceConfig as _SvcCfg
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        payload = _SvcCfg.model_validate(_json.loads(config))
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.update_config(service, payload)
        print(resp.model_dump())


    def service_worker(self, service: str, worker: str, health: str, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """POST a ServiceStatusHealth JSON to a running server for service/worker."""

        import json as _json
        from .client import EigenpulsClient
        from .service import ServiceStatusHealth as _Health
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        payload = _Health.model_validate(_json.loads(health))
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.update_worker(service, worker, payload)
        print(resp.model_dump())

    
    def client_script_name(self) -> str:
        """Print the name of the embedded client script."""

        return CLIENT_SCRIPT_NAME

    def client_script(self) -> str:
        """Print the embedded bash client script to stdout."""

        from importlib.resources import files

        return files("eigenpuls.resources").joinpath(self.client_script_name()).read_text(encoding="utf-8")


def main():
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)



