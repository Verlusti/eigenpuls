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


    def probe_cmd(
        self,
        probe: str,
        service: str,
        worker: str,
        url: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
        apikey_env_var: str = "EIGENPULS_APIKEY",
        script_path: Optional[str] = None,
    ) -> str:
        """Factory: emit a one-liner bash command to run a probe and report.

        - probe: postgres|redis|rabbitmq|http|tcp
        - service/worker: identifiers reported to eigenpuls
        - url: eigenpuls base URL
        - host/port/path: probe target (path only for http)
        - apikey_env_var: environment variable name to read bearer token from
        - script_path: path to the client script (defaults to /opt/eigenpuls-client.sh)
        """

        probe = probe.lower().strip()
        allowed = {"postgres", "redis", "rabbitmq", "http", "tcp"}
        if probe not in allowed:
            raise ValueError(f"unsupported probe: {probe}")
        
        if not url:
            raise ValueError("url is required")

        base_url = url
        script_path = script_path or f"/opt/{self.client_script_name()}"
        envs = [
            "ACTION=probe",
            f"PROBE={probe}",
            f"SERVICE={service}",
            f"WORKER={worker}",
            f"EIGENPULS_URL={base_url}",
            f"EIGENPULS_APIKEY=\${apikey_env_var}",
        ]
        if host:
            envs.append(f"PROBE_HOST={host}")
        if port is not None:
            envs.append(f"PROBE_PORT={port}")
        if probe == "http" and path:
            envs.append(f"PROBE_PATH={path}")
        env_str = " ".join(envs)
        # POSIX sh-compatible one-liner (no bash required)
        cmd = f"{env_str} sh {script_path}"

        return cmd


def main():
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)



