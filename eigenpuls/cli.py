from __future__ import annotations

from .config import AppConfig, get_app_config

import os
from typing import Optional

import fire
import uvicorn


class CLI:

    def __init__(self):
        pass


    def version(self) -> str:
        try:
            from importlib.metadata import version
            return version("eigenpuls")
        except Exception:
            return "0+unknown"


    def serve(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        from .api import app

        config_model = get_app_config()
        host = host or config_model.host
        port = port or config_model.port

        try:
            uvicorn.run(app, host=host, port=port)
        except KeyboardInterrupt:
            pass


    def list_known_types(self) -> None:
        from .service import ServiceKnownType
        print("Known service types:")
        for t in ServiceKnownType:
            print(f"  - {t.value}")


    async def service_list(self) -> None:
        from .api import health_service_list
        
        resp = await health_service_list()
        print(resp)

    
    def current_apikey(self, show: bool = False) -> None:
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
        from .api import health_service_config
        resp = await health_service_config(service, config)
        print(resp)


    async def service_worker(self, service: str, worker: str, health: str) -> None:
        from .api import health_service_worker
        resp = await health_service_worker(service, worker, health)
        print(resp)


    def client_script(self) -> str:
        from importlib.resources import files
        return files("eigenpuls.eigenpuls.resources").joinpath("eigenpuls-client.sh").read_text(encoding="utf-8")


def main():
    import os
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)



