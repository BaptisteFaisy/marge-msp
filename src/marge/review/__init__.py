"""The monthly written review (spec 8.4, 14.4, EF-REV-01..03)."""

from __future__ import annotations

from .aggregates import ClientFigure, ReviewInputs, VariationFigure, build_review_inputs, trend_label
from .fallback import LocalSink, S3Archive, SesMailer, publish, review_key, subject_for
from .narrate import narrate_review, review_with_figures, unknown_figures
from .template import render_review, section_titles

__all__ = [
    "ClientFigure",
    "LocalSink",
    "ReviewInputs",
    "S3Archive",
    "SesMailer",
    "VariationFigure",
    "build_review_inputs",
    "narrate_review",
    "publish",
    "render_review",
    "review_key",
    "review_with_figures",
    "section_titles",
    "subject_for",
    "trend_label",
    "unknown_figures",
]
