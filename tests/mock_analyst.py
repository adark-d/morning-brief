from __future__ import annotations

from dataclasses import dataclass

from ai_brief.models import Brief, Lesson, Selection, Story


@dataclass(frozen=True)
class MockAnalyst:
    topic_count: int = 5
    input_tokens: int = 0
    output_tokens: int = 0

    async def select(self, stories: tuple[Story, ...], interests: str) -> Selection:
        _ = interests
        return Selection(story_ids=tuple(story.id for story in stories[: self.topic_count]))

    async def explain(self, stories: tuple[Story, ...], interests: str) -> Brief:
        _ = interests
        return Brief(
            lessons=tuple(
                Lesson(
                    story_id=story.id,
                    headline=story.title,
                    what_happened=story.summary,
                    why_it_matters="Reliable evaluation helps you decide whether a change works.",
                    concept="Evaluation datasets",
                    explanation="A fixed collection of examples lets you compare system behavior across changes.",
                    example="Run the same ten support questions before and after changing a prompt.",
                    takeaway="Keep representative examples and check outcomes after each change.",
                )
                for story in stories
            )
        )
