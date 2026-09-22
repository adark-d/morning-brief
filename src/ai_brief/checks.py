from __future__ import annotations

from ai_brief.models import Brief, BriefError, Story


def check_ids(ids: tuple[str, ...], stories: tuple[Story, ...], topic_count: int = 5) -> None:
    """Reject repeated, excessive, or unknown IDs; an empty selection is valid."""

    if len(ids) > topic_count or len(set(ids)) != len(ids):
        raise BriefError(f"Selection must contain zero to {topic_count} distinct stories")
    if not set(ids).issubset({story.id for story in stories}):
        raise BriefError("Selection references an unknown source")


def check_brief(
    brief: Brief,
    stories: tuple[Story, ...],
    topic_count: int = 5,
) -> None:
    """Require a complete lesson for every selected story, in order."""

    check_ids(tuple(lesson.story_id for lesson in brief.lessons), stories, topic_count)
    if tuple(lesson.story_id for lesson in brief.lessons) != tuple(story.id for story in stories):
        raise BriefError("Lessons must cover every selected story in order")

    errors: list[str] = []
    for lesson in brief.lessons:
        reader_text = (
            lesson.headline,
            lesson.what_happened,
            lesson.why_it_matters,
            lesson.concept,
            lesson.explanation,
            lesson.example,
            lesson.takeaway,
        )
        if any(not value.strip() for value in reader_text):
            errors.append(f"Story {lesson.story_id}: reader-facing fields cannot be blank")

    # Give the model every correction in one attempt instead of revealing them one at a time.
    if errors:
        raise BriefError("\n".join(errors))
