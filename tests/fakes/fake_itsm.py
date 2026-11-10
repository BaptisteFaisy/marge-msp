"""Ticket-tool double used by the MCP server tests (spec 14.3)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FakeItsm:
    """Records every action instead of calling a real ITSM tool."""

    tasks: dict[str, list[dict]] = field(default_factory=dict)
    drafts: dict[str, list[str]] = field(default_factory=dict)
    fail_on: str | None = None

    def create_renegotiation_task(self, client_id: str, owner_id: str, dossier: str) -> str:
        if self.fail_on == "create_renegotiation_task":
            raise RuntimeError("itsm unavailable")
        task_id = f"task-{client_id}-{len(self.tasks.get(client_id, [])) + 1}"
        self.tasks.setdefault(client_id, []).append(
            {"task_id": task_id, "owner_id": owner_id, "dossier": dossier, "kind": "renegotiation"}
        )
        return task_id

    def open_task_exists(self, client_id: str, kind: str) -> bool:
        return any(t["kind"] == kind for t in self.tasks.get(client_id, []))

    def store_billing_draft(self, client_id: str, proposal: str) -> str:
        if self.fail_on == "store_billing_draft":
            raise RuntimeError("itsm unavailable")
        draft_id = f"draft-{client_id}-{len(self.drafts.get(client_id, [])) + 1}"
        self.drafts.setdefault(client_id, []).append(proposal)
        return draft_id
