"""Two models: the real one on Bedrock, and a deterministic local one.

``BedrockClassifierModel`` uses the Flex inference profile for the nightly
batch (spec 13.2: Flex is cheaper for work that tolerates latency). boto3 is
imported inside the method so the test suite never needs it.

``LocalRuleModel`` is not a fake for tests only: it is the offline fallback of
the demo and the reference the evaluation harness compares against.
"""

from __future__ import annotations

import json

from ..domain import Contract, Intervention
from .prompt import build_prompt

DEFAULT_MODEL_ID = "anthropic.claude-3-5-haiku-20241022-v1:0"

OUT_OF_SCOPE_MARKERS = (
    "développement",
    "developpement",
    "code applicatif",
    "requête sql",
    "requete sql",
    "modification du code",
    "formation",
    "achat de matériel",
    "achat de materiel",
    "projet applicatif",
)

IN_SCOPE_MARKERS = (
    "supervision",
    "monitoring",
    "sauvegarde",
    "restauration",
    "backup",
    "patch",
    "mise à jour système",
    "mise a jour systeme",
    "incident",
    "redémarrage",
    "redemarrage",
    "gestion des accès",
    "gestion des acces",
    "antivirus",
    "certificat",
)


class BedrockClassifierModel:
    """Classifier backed by a Bedrock model, Flex tier, structured output."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = "eu-west-3",
        inference_profile: str = "flex",
        client=None,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.inference_profile = inference_profile
        self._client = client

    def _runtime(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def complete(self, prompt: str, schema: dict) -> str:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._runtime().invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
            # Flex: cheaper nightly batch (spec 13.2)
            performanceConfigLatency=self.inference_profile,
        )
        payload = json.loads(response["body"].read())
        blocks = payload.get("content") or []
        return blocks[0].get("text", "{}") if blocks else "{}"


class LocalRuleModel:
    """Deterministic keyword classifier: offline demo and test reference."""

    model_id = "local-rule-model"

    def __init__(self, out_confidence: float = 0.9, in_confidence: float = 0.95) -> None:
        self.out_confidence = out_confidence
        self.in_confidence = in_confidence
        self.calls: list[str] = []

    def complete(self, prompt: str, schema: dict) -> str:
        self.calls.append(prompt)
        lowered = prompt.lower()
        ticket = lowered.split("<ticket_data>")[-1].split("</ticket_data>")[0]
        scope = lowered.split("<contract_scope>")[-1].split("</contract_scope>")[0]
        if any(marker in ticket for marker in OUT_OF_SCOPE_MARKERS):
            return self._answer("OUT_OF_SCOPE", self.out_confidence, self._clause(scope))
        if any(marker in ticket for marker in IN_SCOPE_MARKERS):
            return self._answer("IN_SCOPE", self.in_confidence, "")
        return self._answer("UNCERTAIN", 0.45, "")

    @staticmethod
    def _clause(scope: str) -> str:
        for line in scope.splitlines():
            if line.startswith("- ") and any(
                word in line for word in ("développement", "code", "formation", "matériel")
            ):
                return f"Exclusions : « {line[2:].strip()} »"
        return "Exclusions du contrat"

    @staticmethod
    def _answer(work_class: str, confidence: float, clause: str) -> str:
        return json.dumps(
            {
                "class": work_class,
                "confidence": confidence,
                "citedClause": clause,
                "reason": "deterministic keyword rules (local model)",
            }
        )


def build_prompt_for(intervention: Intervention, contract: Contract) -> str:
    """Convenience wrapper so callers do not import the prompt module."""
    return build_prompt(intervention, contract)
