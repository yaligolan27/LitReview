"""The HTTP layer — spec §11.1 (apis/_http.py).

One shared Session (connection pooling), retries with backoff honoring
Retry-After, a 7-day disk cache keyed by sha1(url+params) that also caches
404s, and a polite-pool User-Agent carrying the contact email.

The critical distinction (reliability mechanism #4): ``NetworkError`` ("we
could not check") is a different outcome from an empty/404 result ("we
checked and it is not there"). Callers must never treat the first as the
second.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import requests

from ..config import get_settings

_BACKOFFS = (0.8, 1.6, 3.2)
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class NetworkError(RuntimeError):
    """Transient failure — we could NOT check. Never equals 'not found'."""


class NotFoundError(RuntimeError):
    """Definitive 404 — we checked and it does not exist."""


_session: requests.Session | None = None
_session_lock = threading.Lock()


def session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            settings = get_settings()
            s.headers.update({
                "User-Agent": f"litreview/0.1 (mailto:{settings.contact_email})",
                "Accept": "application/json",
            })
            _session = s
        return _session


def reset_session() -> None:
    global _session
    with _session_lock:
        _session = None


def _cache_path(url: str, params: dict[str, Any] | None) -> Path:
    settings = get_settings()
    key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return Path(settings.http_cache_dir) / f"{digest}.json"


def _cache_read(path: Path) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.http_cache:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    if settings.http_cache_ttl and (time.time() - stat.st_mtime) > settings.http_cache_ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_write(path: Path, entry: dict[str, Any]) -> None:
    if not get_settings().http_cache:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # cache is best-effort


def get_json(url: str, params: dict[str, Any] | None = None,
             headers: dict[str, str] | None = None,
             timeout: float | None = None) -> Any:
    """GET with retries + cache. Returns parsed JSON.

    Raises ``NotFoundError`` on 404 (a definitive answer, and cached) and
    ``NetworkError`` on transport failures / retry exhaustion.
    """
    settings = get_settings()
    cache_file = _cache_path(url, params)
    cached = _cache_read(cache_file)
    if cached is not None:
        if cached.get("status") == 404:
            raise NotFoundError(url)
        return cached.get("body")

    timeout = timeout or settings.http_timeout
    attempts = settings.http_retries + 1
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            resp = session().get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if resp.status_code == 404:
                _cache_write(cache_file, {"status": 404, "body": None})
                raise NotFoundError(url)
            if resp.status_code in _RETRY_STATUSES:
                last_error = NetworkError(f"HTTP {resp.status_code} from {url}")
                retry_after = resp.headers.get("Retry-After")
                if retry_after and attempt < attempts - 1:
                    try:
                        time.sleep(min(30.0, float(retry_after)))
                        continue
                    except ValueError:
                        pass
            elif resp.status_code >= 400:
                raise NetworkError(f"HTTP {resp.status_code} from {url}")
            else:
                try:
                    body = resp.json()
                except ValueError as exc:
                    raise NetworkError(f"non-JSON response from {url}: {exc}") from exc
                _cache_write(cache_file, {"status": resp.status_code, "body": body})
                return body
        if attempt < attempts - 1:
            time.sleep(_BACKOFFS[min(attempt, len(_BACKOFFS) - 1)])

    raise NetworkError(f"GET {url} failed after {attempts} attempts: {last_error}")
