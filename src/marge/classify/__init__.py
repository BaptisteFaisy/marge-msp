"""Intervention classification against a contract scope (spec 9.3, 13.2)."""

from __future__ import annotations

from .bedrock import BedrockClassifierModel, LocalRuleModel
from .memory import DecisionMemory, decided_class, is_decided
from .output import InvalidModelOutput, parse_model_output, to_annex_c
from .prompt import OUTPUT_SCHEMA, build_prompt, sanitise
from .service import classify, classify_batch

__all__ = [
    "OUTPUT_SCHEMA",
    "BedrockClassifierModel",
    "DecisionMemory",
    "InvalidModelOutput",
    "LocalRuleModel",
    "build_prompt",
    "classify",
    "classify_batch",
    "decided_class",
    "is_decided",
    "parse_model_output",
    "sanitise",
    "to_annex_c",
]
