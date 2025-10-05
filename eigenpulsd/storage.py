from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional

try:
    # UltraDict provides a dict-like shared memory store with inter-process lock
    from UltraDict import UltraDict  # type: ignore
except Exception as e:  # pragma: no cover
    UltraDict = None  # type: ignore


_STORE: Optional["UltraDict"] = None
_STORE_NAME: Optional[str] = None


def _shared_name() -> str:
    global _STORE_NAME
    if _STORE_NAME:
        return _STORE_NAME
    try:
        from eigenpulsd.config import AppConfig
        cfg = AppConfig()
        _STORE_NAME = cfg.shared_name
        return _STORE_NAME
    except Exception:
        # Safe fallback
        return "eigenpuls_shared_store"


def init_store(name: Optional[str] = None) -> None:
    global _STORE
    if UltraDict is None:
        raise RuntimeError("UltraDict package is not installed")
    if _STORE is not None:
        return
    store_name = name or _shared_name()
    # shared_lock enables cross-process synchronization
    _STORE = UltraDict(name=store_name, shared_lock=True)


def get_store() -> "UltraDict":
    if UltraDict is None:
        raise RuntimeError("UltraDict package is not installed")
    global _STORE
    if _STORE is None:
        init_store()
    assert _STORE is not None
    return _STORE


@contextmanager
def with_store_lock() -> Iterator[None]:
    store = get_store()
    lock = getattr(store, "lock", None)
    if lock is None:
        # Fallback: no-op if UltraDict version lacks lock
        yield
        return
    with lock:
        yield


def set_value(key: str, value: Any) -> None:
    store = get_store()
    store[key] = value


def get_value(key: str, default: Any = None) -> Any:
    store = get_store()
    return store.get(key, default)


