-- Idea 18: append-only log of every model call (ENF-IA-01..03).
-- One row per invocation; the payload is the JSON of marge.domain.LlmCall.

CREATE TABLE IF NOT EXISTS llm_calls (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);

-- Idea 28 / EF-CAL-03: history of calculation versions. A change of hourly
-- cost or allocation rule opens a new version; past versions stay readable.
CREATE TABLE IF NOT EXISTS calc_versions (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
