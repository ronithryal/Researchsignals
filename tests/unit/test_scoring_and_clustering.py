from datetime import datetime, timedelta, timezone
from typing import cast

from app.clustering import _choose_k
from app.models import Post
from app.scoring import _engagement_component, _semantic_component, _temporal_component


class DummyPost:
    def __init__(self, text_content: str = "", engagement_score: float = 0.0, posted_at=None):
        self.text_content = text_content
        self.engagement_score = engagement_score
        self.posted_at = posted_at


def test_choose_k_respects_bounds():
    assert _choose_k(2) == 2
    assert _choose_k(1000) == 15


def test_engagement_component_averages_scores():
    posts = [DummyPost(engagement_score=0.2), DummyPost(engagement_score=0.8)]
    assert _engagement_component(cast(list[Post], posts)) == 0.5


def test_temporal_component_favors_newer_posts():
    now = datetime.now(timezone.utc)
    newer = [DummyPost(posted_at=now - timedelta(hours=1))]
    older = [DummyPost(posted_at=now - timedelta(days=14))]

    assert _temporal_component(cast(list[Post], newer)) > _temporal_component(cast(list[Post], older))


def test_semantic_component_rewards_defi_keyword_density():
    high_signal = [DummyPost(text_content="defi yield liquidity protocol dao")]
    low_signal = [DummyPost(text_content="hello world random words only")]

    assert _semantic_component(cast(list[Post], high_signal)) > _semantic_component(cast(list[Post], low_signal))
