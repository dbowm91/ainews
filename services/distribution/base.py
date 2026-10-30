"""Small typed contract for the sole supported delivery transport."""
from dataclasses import dataclass
from typing import Literal, Protocol

OutcomeCode = Literal["accepted", "temporary_failure", "permanent_failure", "unknown", "suppressed"]


@dataclass(frozen=True)
class DeliveryOutcome:
    code: OutcomeCode
    error_code: str | None = None
    reference: str | None = None


class DeliveryChannel(Protocol):
    key: str
    def send(self, intent_id: int) -> DeliveryOutcome: ...
