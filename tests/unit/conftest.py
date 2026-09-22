from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from ai_brief.models import Issue, Story


@pytest.fixture
def issue() -> Issue:
    return Issue(
        collected_at=datetime(2026, 9, 21, tzinfo=UTC),
        stories=(
            Story(
                id="one",
                source="tldr",
                source_url=HttpUrl("https://tldr.tech/ai/2026-09-21"),
                published_at=datetime(2026, 9, 21, tzinfo=UTC),
                title="Evaluations for builders",
                url=HttpUrl("https://example.org/evals"),
                summary="Fixed evaluation datasets help compare behavior before and after a change.",
            ),
        ),
    )
