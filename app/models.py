"""Result types shared by the checks and the API."""

from dataclasses import asdict, dataclass, field
from enum import Enum


class Status(str, Enum):
    MATCH = "match"
    REVIEW = "review"
    MISMATCH = "mismatch"
    NOT_CHECKED = "not_checked"


# Worst status wins when several checks are rolled up into one.
_SEVERITY = {Status.NOT_CHECKED: 0, Status.MATCH: 1, Status.REVIEW: 2, Status.MISMATCH: 3}


def worst(statuses) -> Status:
    statuses = list(statuses)
    if not statuses:
        return Status.NOT_CHECKED
    return max(statuses, key=_SEVERITY.__getitem__)


@dataclass
class Check:
    key: str
    label: str
    status: Status
    message: str
    expected: str | None = None
    found: str | None = None


@dataclass
class Difference:
    expected: str  # words the regulation requires ("" if the label added words)
    found: str  # words read from the label ("" if the label is missing words)


@dataclass
class WarningResult:
    status: Status
    message: str
    checks: list[Check]
    found_text: str | None = None
    differences: list[Difference] = field(default_factory=list)


@dataclass
class Verification:
    verdict: str  # "pass" | "review" | "fail"
    headline: str
    fields: list[Check]
    warning: WarningResult
    ocr_text: str
    elapsed_ms: int

    def to_dict(self) -> dict:
        return asdict(self)
