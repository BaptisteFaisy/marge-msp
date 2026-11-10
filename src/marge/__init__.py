"""Marge — per-client profitability for managed service providers.

Built for the AWS MSP AI Hackathon (Track 1, Best Amazon Quick Application).
The package is organised in layers:

``domain``  pure dataclasses and value objects (no I/O, no dependency)
``calc``    the margin model of spec chapter 12 (pure functions)
``ingest``  replaceable source connectors
``contracts`` / ``classify`` / ``match``  the three AI-assisted steps,
            each one validated by a human before it counts
``store``   persistence (sqlite locally, DynamoDB on AWS)
``api``     validation portal API
``mcp``     the agent's action server
``review``  the monthly written review
``quicksight``  datasets, topic, dashboards, RLS, scenarios, agent, flows
``eval``    accuracy harnesses for the four measured AI steps
``pipeline``    nightly / weekly / monthly orchestration
"""

from __future__ import annotations

__version__ = "0.1.0"
