from __future__ import annotations

from .service.base import Service, KnownServiceType
from .service.registry import service_registry

import os
from pathlib import Path
from typing import List, Any, Dict

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_PORT = 4242
DEFAULT_HOST = "0.0.0.0"
DEFAULT_INTERVAL_SECONDS = 10


class AppConfig(BaseSettings):
    port: int = DEFAULT_PORT
    host: str = DEFAULT_HOST
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    services: List[Service] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="EIGENPULS",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        arbitrary_types_allowed=True,
    )

    @field_validator("services", mode="before")
    @classmethod
    def _build_services(cls, value: Any) -> List[Service]:
        from .service import models as _register_services

        if value is None:
            return []
        if isinstance(value, list):
            built: List[Service] = []
            for item in value:
                if isinstance(item, Service):
                    built.append(item)
                    continue
                if not isinstance(item, dict):
                    raise TypeError("Each service must be a mapping with at least 'name' and 'type'")
                type_str = item.get("type")
                name = item.get("name")
                if not type_str or not name:
                    raise ValueError("Service entries require 'name' and 'type'")
                try:
                    svc_type = KnownServiceType(type_str)
                except Exception:
                    raise ValueError(f"Unknown service type: {type_str}")
                svc_cls = service_registry.get(svc_type)
                svc = svc_cls(name=name)
                # assign remaining fields to the service instance
                for key, val in item.items():
                    if key in {"name", "type"}:
                        continue
                    setattr(svc, key, val)
                built.append(svc)
            return built
        raise TypeError("services must be a list")


    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        def yaml_settings_source():
            path = os.environ.get("EIGENPULS_CONFIG")
            if not path:
                return {}
            try:
                with open(Path(path), "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except FileNotFoundError:
                return {}

        # Order: init kwargs -> YAML -> env -> .env -> secrets
        return (
            init_settings,
            yaml_settings_source,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


    def dockerfile(self) -> str:
        from importlib.resources import files
        from eigenpuls import __version__

        dockerfile = files("eigenpuls.resources").joinpath("Dockerfile.eigenpuls").read_text(encoding="utf-8")
        dockerfile = dockerfile.replace("${EIGENPULS_VERSION}", __version__)
        return dockerfile