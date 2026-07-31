"""Small, serialisable models for explainable editorial research leads."""

from dataclasses import asdict, dataclass, field
from hashlib import sha1
import json


VALID_STATUSES = {
    "confirmed", "conditional", "record_equalled", "record_broken",
    "approaching_milestone", "coverage_limited", "approximate",
}


@dataclass
class Insight:
    insight_type: str
    category: str
    status: str
    subject_type: str
    subject_id: str
    subject_name: str
    title: str
    summary: str
    scope: dict
    metric: dict
    comparison: dict | None = None
    condition: dict | None = None
    editorial_score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    confidence: float = 1.0
    coverage_warning: str | None = None
    evidence: list = field(default_factory=list)
    data_as_of: str | None = None
    detector: str = ""
    detector_version: str = "1.0"
    id: str = ""

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Unsupported insight status: {self.status}")
        if not self.id:
            identity = {
                "type": self.insight_type, "subject": self.subject_id,
                "scope": self.scope, "metric": self.metric, "condition": self.condition,
            }
            digest = sha1(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:14]
            self.id = f"insight-{digest}"

    def to_dict(self):
        return asdict(self)
