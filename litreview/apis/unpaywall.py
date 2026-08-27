"""Unpaywall connector — open-access PDF locations for full-text retrieval
(spec §9.5)."""

from __future__ import annotations

from ..config import get_settings
from . import _http

BASE = "https://api.unpaywall.org/v2"


def best_pdf_url(doi: str) -> str:
    if not doi:
        return ""
    try:
        data = _http.get_json(f"{BASE}/{doi}",
                              params={"email": get_settings().contact_email})
    except (_http.NotFoundError, _http.NetworkError):
        return ""
    location = (data or {}).get("best_oa_location") or {}
    return location.get("url_for_pdf") or ""
