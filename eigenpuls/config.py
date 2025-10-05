from uuid import uuid4
from typing import Optional
from pydantic import SecretStr
import threading

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_PORT = 4242
DEFAULT_HOST = "0.0.0.0"
DEFAULT_DEBUG = False
DEFAULT_APIKEY = str(uuid4())
DEFAULT_SHARED_NAME = "eigenpuls_shared_store"


class AppConfig(BaseSettings):
    port: int = DEFAULT_PORT
    host: str = DEFAULT_HOST
    debug: bool = DEFAULT_DEBUG
    apikey: SecretStr = SecretStr(DEFAULT_APIKEY)
    shared_name: Optional[str] = DEFAULT_SHARED_NAME

    model_config = SettingsConfigDict(
        env_prefix="EIGENPULS_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        arbitrary_types_allowed=True,
    )


# Global accessor for configuration loaded once and cached
_APP_CONFIG: Optional[AppConfig] = None
_APP_CONFIG_LOCK = threading.Lock()


def get_app_config(reload: bool = False) -> AppConfig:
    global _APP_CONFIG
    if reload:
        with _APP_CONFIG_LOCK:
            _APP_CONFIG = AppConfig()
            return _APP_CONFIG
    if _APP_CONFIG is None:
        with _APP_CONFIG_LOCK:
            if _APP_CONFIG is None:
                _APP_CONFIG = AppConfig()
    return _APP_CONFIG  

