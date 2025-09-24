from .base import KnownServiceType, Service

from typing import Dict, Type
from threading import Lock


class ServiceRegistry:

    def __init__(self):
        self._services: Dict[KnownServiceType, Type[Service]] = {}
        self._services_lock = Lock()


    def register(self, service_type: KnownServiceType, service_class: Type[Service]):
        with self._services_lock:
            self._services[service_type] = service_class


    def get(self, service_type: KnownServiceType) -> Type[Service]:
        with self._services_lock:
            return self._services[service_type] 


service_registry = ServiceRegistry()