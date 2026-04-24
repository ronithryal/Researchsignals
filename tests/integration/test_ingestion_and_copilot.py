from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, text

from app.config import settings
from app.copilot import generate_brief
from app.db import engine, get_session
from app.ingestion import fetch_new_posts
from app.models import Account, IngestionRun, Post, SignalCluster, post_clusters


async def _clear_core_tables(db):
    await db.execute(delete(post_clusters))
    await db.execute(delete(SignalCluster))
    await db.execute(delete(Post))
    await db.execute(delete(Account))
    await db.execute(delete(IngestionRun))
    await db.commit()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def require_postgres():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Integration tests require a running Postgres database", allow_module_level=True)


@pytest.mark.asyncio
async def test_ingestion_no_accounts_creates_completed_run():
    async with get_session() as db:
        await _clear_core_tables(db)

    posts = await fetch_new_posts()
    assert posts == []

    async with get_session() as db:
        latest = (
            await db.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
        ).scalar_one_or_none()

        assert latest is not None
        assert latest.status == "completed"
        assert latest.posts_ingested == 0
        assert latest.posts_new == 0


@pytest.mark.asyncio
async def test_generate_brief_returns_model_output(monkeypatch):
    async with get_session() as db:
        await _clear_core_tables(db)

        account = Account(
            x_id="acct-1",
            username="alice",
            display_name="Alice",
            follower_count=10,
        )
        db.add(account)
        await db.flush()

        post = Post(
            x_id="tweet-1",
            canonical_x_url="https://x.com/alice/status/1",
            account_id=account.id,
            text_content="DeFi protocol yield update",
            engagement_score=0.7,
            likes_count=5,
            retweets_count=1,
            replies_count=0,
            posted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(post)
        await db.flush()

        cluster = SignalCluster(
            name="Signal: defi",
            topic="defi",
            primary_x_url=post.canonical_x_url,
            research_alpha_score=0.8,
            post_count=1,
        )
        db.add(cluster)
        await db.flush()
        await db.execute(insert(post_clusters).values(post_id=post.id, cluster_id=cluster.id))
        await db.commit()

    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    class _FakeUsage:
        output_tokens = 42

    class _FakeText:
        text = "Summary with citation (source: https://x.com/alice/status/1)"

    class _FakeResponse:
        content = [_FakeText()]
        usage = _FakeUsage()

    class _FakeMessages:
        async def create(self, **kwargs):
            return _FakeResponse()

    class _FakeAnthropicClient:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", _FakeAnthropicClient)

    brief = await generate_brief(cluster.id)
    assert "source: https://x.com/alice/status/1" in brief
