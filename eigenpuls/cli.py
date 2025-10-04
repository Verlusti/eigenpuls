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

    
    def current_apikey(self) -> None:
        from .api import _get_expected_apikey

        print(f"Current API key: {_get_expected_apikey()}")


def main():
    import os
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)



