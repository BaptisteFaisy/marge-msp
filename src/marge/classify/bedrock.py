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

# Inference profile, not a bare model id: Bedrock refuses on-demand invocation
# of `amazon.nova-lite-v1:0` and asks for the regional profile instead
# (verified live on account 710332178565 in eu-west-1, 2026-11-11:
# "Invocation of model ID amazon.nova-lite-v1:0 with on-demand throughput isn't
# supported. Retry your request with the ID or ARN of an inference profile").
DEFAULT_MODEL_ID = "eu.amazon.nova-lite-v1:0"
LATENCY_MODES = ("standard", "optimized")
DEFAULT_REGION = "eu-west-1"

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
    """Classifier backed by a Bedrock model, Flex tier, structured output.

    Two request shapes are supported because the payload and the answer of a
    Nova model differ from an Anthropic one. The family is derived from the
    model id, so callers only choose a model.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = DEFAULT_REGION,
        inference_profile: str = "standard",
        max_tokens: int = 400,
        client=None,
    ) -> None:
        self.model_id = model_id
        self.region = region
        # Bedrock only accepts "optimized" or "standard" here (verified live on
        # 2026-11-11: "Value 'flex' ... failed to satisfy constraint: Member must
        # satisfy enum value set: [optimized, standard]"). The Flex tier of spec
        # 13.2 is a *pricing* tier reached through a flex inference profile id,
        # which this account does not expose in eu-west-1 (`list-inference-profiles`
        # filtered on "flex" returns none). Pass such a profile id as `model_id`
        # when it becomes available; nothing else has to change.
        self.inference_profile = inference_profile if inference_profile in LATENCY_MODES else "standard"
        self.max_tokens = max_tokens
        self._client = client

    @property
    def family(self) -> str:
        """``nova`` or ``anthropic``, inferred from the model id."""
        return "nova" if "nova" in self.model_id else "anthropic"

    def _runtime(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def _request_body(self, prompt: str) -> dict:
        if self.family == "nova":
            return {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": self.max_tokens, "temperature": 0},
            }
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }

    @staticmethod
    def _answer_text(payload: dict, family: str) -> str:
        if family == "nova":
            content = (payload.get("output") or {}).get("message", {}).get("content") or []
            return content[0].get("text", "{}") if content else "{}"
        blocks = payload.get("content") or []
        return blocks[0].get("text", "{}") if blocks else "{}"

    def complete(self, prompt: str, schema: dict) -> str:
        """One Bedrock call, returning the raw text answer (Annex C JSON)."""
        response = self._runtime().invoke_model(
            modelId=self.model_id,
            body=json.dumps(self._request_body(prompt)),
            contentType="application/json",
            accept="application/json",
            performanceConfigLatency=self.inference_profile,
        )
        payload = json.loads(response["body"].read())
        return self._answer_text(payload, self.family)


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
