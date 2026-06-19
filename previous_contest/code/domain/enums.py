"""Domain enums — all constrained value sets live here.

Import from this module everywhere. Never use string literals for domain
values directly in agent or pipeline code.
"""
from enum import Enum


class Domain(str, Enum):
    HACKERRANK = "hackerrank"
    CLAUDE = "claude"
    VISA = "visa"
    UNKNOWN = "unknown"

    @classmethod
    def from_company(cls, company: str) -> "Domain":
        mapping = {
            "hackerrank": cls.HACKERRANK,
            "claude": cls.CLAUDE,
            "visa": cls.VISA,
            "none": cls.UNKNOWN,
        }
        return mapping.get(company.lower(), cls.UNKNOWN)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def is_auto_escalate(self) -> bool:
        return self in (RiskLevel.HIGH, RiskLevel.CRITICAL)


class TicketStatus(str, Enum):
    REPLIED = "replied"
    ESCALATED = "escalated"


class RequestType(str, Enum):
    PRODUCT_ISSUE = "product_issue"
    FEATURE_REQUEST = "feature_request"
    BUG = "bug"
    INVALID = "invalid"


class CognitiveLoad(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
