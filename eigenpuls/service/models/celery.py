from eigenpuls.service.base import (
    Service,
    KnownServiceType,
    ServiceStatus,
    ServiceHealth,
    SystemPackageType,
)
from eigenpuls.service.registry import service_registry

from typing import List, Optional, Tuple
import asyncio
import urllib.request
import urllib.error
import json


class CeleryWorkerService(Service):
    
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_WORKER, **data)


    async def run(self) -> ServiceStatus:
        # Query mini health server started inside the Celery worker process (fully async)
        host = self.host or "localhost"
        port = int(self.port or 8099)
        path = "/health"
        url = f"http://{host}:{port}{path}"
        self._last_command = f"GET {url}"
        try:
            status_code, body = await _http_get(host, port, path, timeout=self.timeout or 10)
            if status_code >= 400:
                return ServiceStatus(status=ServiceHealth.ERROR, details=f"http {status_code}")
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                return ServiceStatus(status=ServiceHealth.ERROR, details="invalid json from health endpoint")

            broker_ok = str(payload.get("broker", "")).lower() == "ok"
            worker_ping = str(payload.get("worker_ping", "")).lower() == "ok"
            overall = str(payload.get("status", "")).lower() == "ok"
            if overall and broker_ok and worker_ping:
                return ServiceStatus(status=ServiceHealth.OK, details="celery worker health ok")
            details = payload.get("details") or ""
            if not details:
                details = f"overall={overall} broker={broker_ok} worker_ping={worker_ping}"
            return ServiceStatus(status=ServiceHealth.ERROR, details=details)
        except Exception as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=str(e))


    def build_command(self) -> str:
        return self.replace_placeholders("GET http://%host%:%port%/health")


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                return []
        raise ValueError(f"Unsupported package type: {package_type}")


class CeleryBeatService(Service):
    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_BEAT, **data)


    async def run(self) -> ServiceStatus:
        # Query mini health server started inside the Celery beat process (fully async)
        host = self.host or "localhost"
        port = int(self.port or 8099)
        path = "/health"
        url = f"http://{host}:{port}{path}"
        self._last_command = f"GET {url}"
        try:
            status_code, body = await _http_get(host, port, path, timeout=self.timeout or 10)
            if status_code >= 400:
                return ServiceStatus(status=ServiceHealth.ERROR, details=f"http {status_code}")
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                return ServiceStatus(status=ServiceHealth.ERROR, details="invalid json from health endpoint")

            broker_ok = str(payload.get("broker", "")).lower() == "ok"
            overall = str(payload.get("status", "")).lower() == "ok"
            if overall and broker_ok:
                return ServiceStatus(status=ServiceHealth.OK, details="celery beat health ok")
            details = payload.get("details") or ""
            if not details:
                details = f"overall={overall} broker={broker_ok}"
            return ServiceStatus(status=ServiceHealth.ERROR, details=details)
        except Exception as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=str(e))



    def build_command(self) -> str:
        return self.replace_placeholders("GET http://%host%:%port%/health")


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        match package_type:
            case SystemPackageType.APT:
                return []
        raise ValueError(f"Unsupported package type: {package_type}")


class CeleryFlowerService(Service):

    def __init__(self, name: str, **data):
        super().__init__(name=name, type=KnownServiceType.CELERY_FLOWER, **data)


    async def run(self) -> ServiceStatus:
        # Use Python stdlib HTTP client to query Flower API
        url = self.replace_placeholders("http://%host%:%port%/")
        try:
            loop = asyncio.get_running_loop()
            timeout_seconds = self.timeout or 10
            def _fetch() -> int:
                with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
                    return resp.getcode() or 0
            status_code = await loop.run_in_executor(None, _fetch)
            if status_code < 500:
                return ServiceStatus(status=ServiceHealth.OK, details="flower http ok")
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"flower http {status_code}")
        except urllib.error.HTTPError as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=f"flower http {e.code}")
        except Exception as e:
            return ServiceStatus(status=ServiceHealth.ERROR, details=str(e))


    def build_command(self) -> str:
        return self.replace_placeholders("GET http://%host%:%port%/")


    def get_system_packages(self, package_type: SystemPackageType) -> List[str]:
        # No external packages required when using Python stdlib HTTP
        match package_type:
            case SystemPackageType.APT:
                return []
        raise ValueError(f"Unsupported package type: {package_type}")


service_registry.register(KnownServiceType.CELERY_WORKER, CeleryWorkerService)
service_registry.register(KnownServiceType.CELERY_BEAT, CeleryBeatService)
service_registry.register(KnownServiceType.CELERY_FLOWER, CeleryFlowerService)


async def _http_get(host: str, port: int, path: str, timeout: int) -> Tuple[int, bytes]:
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: eigenpuls/1\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(request.encode("utf-8"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(-1), timeout=timeout)
        # Parse minimal HTTP response
        header_end = raw.find(b"\r\n\r\n")
        if header_end == -1:
            return 0, b""
        header = raw[:header_end].decode("iso-8859-1")
        body = raw[header_end + 4 :]
        status_line = header.splitlines()[0]
        parts = status_line.split()
        status_code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        return status_code, body
    finally:
        try:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
        except Exception:
            pass
