-- Starter schema. Intentionally naive — candidate TODOs marked below.
-- Candidates: add migrations in db/migrations/ (numbered .sql files) and note
-- them in DESIGN.md. Do not edit seed canonical rows to make evals pass.
--
-- Known starter flaws (fix the ones that matter for your agent):
--   1. Dates stored as TEXT in mixed formats (see seed). Normalize on read or
--      migrate to DATE/TIMESTAMPTZ.
--   2. No foreign keys, no indexes beyond PKs. search + order history are slow.
--   3. documents has one row per doc, no chunks, no tsvector, no embeddings.
--      Build your retrieval layer on top (see src/retrieval.py).
--   4. tickets has no dedup constraint. Add one + list-before-create in code.

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    account_status TEXT NOT NULL,
    product_code TEXT NOT NULL,
    region_code TEXT NOT NULL,
    subscription_id TEXT NOT NULL,
    -- BAD (intentional): free-text date, mixed formats.
    created_at TEXT NOT NULL DEFAULT 'Jan 5 2025'
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    -- BAD (intentional): TEXT date, MM/DD/YY.
    started_on TEXT NOT NULL,
    cycle TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    -- BAD (intentional): no FK to customers.
    customer_id TEXT NOT NULL,
    item TEXT NOT NULL,
    -- Mixed formats: mostly ISO, some US short. Normalize in tool layer.
    placed_on TEXT NOT NULL,
    status TEXT NOT NULL,
    total_usd NUMERIC NOT NULL
);
-- TODO (candidate): CREATE INDEX on orders(customer_id, placed_on) if history is slow.

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'current',
    trust TEXT NOT NULL DEFAULT 'official',
    effective_from TEXT NOT NULL DEFAULT '2024-01-01',
    -- customer_facing docs may be quoted to users; internal docs must not be.
    audience TEXT NOT NULL DEFAULT 'customer_facing',
    version INT NOT NULL DEFAULT 1,
    PRIMARY KEY (doc_id, version)
);
-- TODO (candidate): add tsvector + GIN index, or a chunks table + embeddings.
-- Example (don't just paste — decide what your retrieval needs):
--   ALTER TABLE documents ADD COLUMN body_tsv tsvector
--     GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED;
--   CREATE INDEX documents_tsv_idx ON documents USING GIN (body_tsv);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    started_on TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    issue TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    related_order_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- TODO (candidate): add a partial unique index to prevent open dupes, e.g.
--   CREATE UNIQUE INDEX tickets_open_dedup
--     ON tickets (customer_id, related_order_id) WHERE status = 'open';
-- Plus code-level list-before-create + confirm-before-create for UX.

CREATE TABLE IF NOT EXISTS tool_audit_log (
    id SERIAL PRIMARY KEY,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}',
    result_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Atomic ticket numbering (count-then-insert races under concurrency).
CREATE SEQUENCE IF NOT EXISTS ticket_seq START 2001;

-- Read-only role used ONLY by the agent's run_sql tool.
-- Even if sandboxing fails, this role cannot mutate seed data.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_readonly') THEN
        CREATE ROLE agent_readonly LOGIN PASSWORD 'readonlydev';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE support TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_readonly;
-- Audit log is append-only for the readonly role so sandbox use is traceable.
GRANT INSERT ON tool_audit_log TO agent_readonly;
GRANT USAGE, SELECT ON SEQUENCE tool_audit_log_id_seq TO agent_readonly;
-- The agent must retrieve docs via search_docs (the retrieval build), not by
-- SQLing the corpus directly — so the readonly role cannot read documents.
REVOKE SELECT ON documents FROM agent_readonly;
