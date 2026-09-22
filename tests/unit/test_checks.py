from __future__ import annotations

import pytest

from ai_brief.checks import check_brief, check_ids
from ai_brief.models import BriefError, Issue
from tests.mock_analyst import MockAnalyst


@pytest.mark.parametrize("ids", [("missing",), ("one", "one")])
def test_check_ids_invalid_selection_rejects(issue: Issue, ids: tuple[str, ...]) -> None:
    with pytest.raises(BriefError):
        check_ids(ids, issue.stories)


async def test_check_brief_missing_selected_story_rejects(issue: Issue) -> None:
    stories = (*issue.stories, issue.stories[0].model_copy(update={"id": "two"}))
    brief = await MockAnalyst().explain(issue.stories, "evals")
    with pytest.raises(BriefError, match="every selected story"):
        check_brief(brief, stories)


def test_check_ids_empty_selection_is_valid(issue: Issue) -> None:
    check_ids((), issue.stories)


async def test_check_brief_whitespace_fields_rejects(issue: Issue) -> None:
    brief = await MockAnalyst().explain(issue.stories, "evals")
    lesson = brief.lessons[0].model_copy(update={"explanation": "   "})
    with pytest.raises(BriefError, match="one: reader-facing fields cannot be blank"):
        check_brief(brief.model_copy(update={"lessons": (lesson,)}), issue.stories)
