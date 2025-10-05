from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
import asyncio

from eigenpuls.service import (
    ServiceResponse,
    ServiceListResponse,
    ServiceWorkerResponse,
    ServiceStatusHealth,
    ServiceConfig,
)


class EigenpulsError(Exception):
    pass


class EigenpulsClient:
    def __init__(self, base_url: str = "http://127.0.0.1:4242", apikey: Optional[str] = None, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.apikey = apikey
        self.timeout = timeout

    # ----------------------
    # Internal HTTP helpers
    # ----------------------
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.apikey:
            headers["Authorization"] = f"Bearer {self.apikey}"
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        data: Optional[bytes] = None
        headers = self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url=url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                detail = str(e)
            raise EigenpulsError(f"HTTP {e.code} {e.reason}: {detail}") from None
        except urllib.error.URLError as e:
            raise EigenpulsError(str(e)) from None

    async def _arequest(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._request(method, path, body))

    # ------------------
    # Parsing utilities
    # ------------------
    @staticmethod
    def _parse_service_response(data: Dict[str, Any]) -> ServiceResponse:
        return ServiceResponse.model_validate(data)

    @staticmethod
    def _parse_service_list_response(data: Dict[str, Any]) -> ServiceListResponse:
        return ServiceListResponse.model_validate(data)

    @staticmethod
    def _parse_service_worker_response(data: Dict[str, Any]) -> ServiceWorkerResponse:
        return ServiceWorkerResponse.model_validate(data)

    # -------------
    # Sync methods
    # -------------
    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def list_services(self) -> ServiceListResponse:
        data = self._request("GET", "/health/service")
        return self._parse_service_list_response(data)

    def get_service(self, service_name: str) -> ServiceResponse:
        data = self._request("GET", f"/health/service/{service_name}")
        return self._parse_service_response(data)

    def update_config(self, service_name: str, config: ServiceConfig) -> ServiceResponse:
        payload = config.model_dump()
        data = self._request("POST", f"/health/service/{service_name}/config", body=payload)
        return self._parse_service_response(data)

    def update_worker(self, service_name: str, worker_name: str, health: ServiceStatusHealth) -> ServiceWorkerResponse:
        payload = health.model_dump()
        data = self._request("POST", f"/health/service/{service_name}/worker/{worker_name}", body=payload)
        return self._parse_service_worker_response(data)

    # --------------
    # Async methods
    # --------------
    async def ahealth(self) -> Dict[str, Any]:
        return await self._arequest("GET", "/health")

    async def alist_services(self) -> ServiceListResponse:
        data = await self._arequest("GET", "/health/service")
        return self._parse_service_list_response(data)

    async def aget_service(self, service_name: str) -> ServiceResponse:
        data = await self._arequest("GET", f"/health/service/{service_name}")
        return self._parse_service_response(data)

    async def aupdate_config(self, service_name: str, config: ServiceConfig) -> ServiceResponse:
        payload = config.model_dump()
        data = await self._arequest("POST", f"/health/service/{service_name}/config", body=payload)
        return self._parse_service_response(data)

    async def aupdate_worker(self, service_name: str, worker_name: str, health: ServiceStatusHealth) -> ServiceWorkerResponse:
        payload = health.model_dump()
        data = await self._arequest("POST", f"/health/service/{service_name}/worker/{worker_name}", body=payload)
        return self._parse_service_worker_response(data)


