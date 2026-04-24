import pytest
import httpx
from typing import Any, cast

from app.config import settings
from app.ingestion import _fetch_with_provider_fallback, _request_with_retries


class _FakeClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    async def request(self, method, url, **kwargs):
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_request_with_retries_eventually_succeeds():
    req = httpx.Request("GET", "https://example.com")
    client = _FakeClient(
        [
            httpx.ConnectError("boom-1", request=req),
            httpx.ConnectError("boom-2", request=req),
            httpx.Response(200, request=req, json={"ok": True}),
        ]
    )

    resp = await _request_with_retries(
        cast(Any, client),
        "GET",
        "https://example.com",
        retries=2,
        retry_backoff_seconds=0.0,
    )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_provider_fallback_uses_secondary_provider(monkeypatch):
    monkeypatch.setattr(settings, "enable_provider_fallback", True)

    async def _fail_primary(_handles):
        raise RuntimeError("primary down")

    async def _ok_secondary(_handles):
        return [{"tweet_id": "1", "canonical_x_url": "https://x.com/a/status/1"}]

    monkeypatch.setattr("app.ingestion._apify_fetch", _fail_primary)
    monkeypatch.setattr("app.ingestion._xapi_fetch", _ok_secondary)

    source, rows = await _fetch_with_provider_fallback("apify", ["alice"])

    assert source == "apify->xapi"
    assert len(rows) == 1
