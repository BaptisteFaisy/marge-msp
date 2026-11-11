"""Record of one model call (spec 11.3, ENF-IA-01..03).

Every figure Marge shows comes from code, and every AI step is validated by a
human. This record is what makes both claims auditable: it says which model was
asked, when, for what, how long it took, what it cost, and what the human did
with the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(slots=True)
class LlmCall:
    """One model invocation, traced end to end."""

    purpose: str
    """``classify``, ``extract``, ``narrate`` or ``answer``."""

    model_id: str
    entity_kind: str = ""
    entity_id: str = ""
    client_id: str = ""
    contract_id: str = ""
    outcome: str = ""
    """The class or status the call produced, before any human decision."""

    success: bool = True
    error: str = ""
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_estimated: bool = False
    cost_usd: Decimal = Decimal("0")
    injection_detected: bool = False
    injection_patterns: tuple[str, ...] = ()
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def key(self) -> str:
        """Stable identity for upsert-free append logs."""
        return f"{self.at.isoformat()}:{self.purpose}:{self.entity_id}"
