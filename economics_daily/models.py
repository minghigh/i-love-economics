from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceArticle:
    id: str
    title: str
    source: str
    link: str
    published_at: datetime
    content_html: str
    content_text: str


@dataclass
class Topic:
    title: str
    pass_: bool
    score: int
    economic_question: str
    core_concept: str
    reason: str
    source_ids: list[str]
    related_concepts: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "title": self.title,
            "pass": self.pass_,
            "score": self.score,
            "economic_question": self.economic_question,
            "core_concept": self.core_concept,
            "reason": self.reason,
            "source_ids": self.source_ids,
            "related_concepts": self.related_concepts,
        }
