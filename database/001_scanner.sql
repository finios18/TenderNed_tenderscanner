-- Run as database administrator (Supabase SQL Editor), once per database.
-- This schema is private: do NOT add it to Supabase's exposed API schemas.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scanner_worker') THEN
    CREATE ROLE scanner_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS scanner;
REVOKE ALL ON SCHEMA scanner FROM PUBLIC;
GRANT USAGE ON SCHEMA scanner TO scanner_worker;

CREATE TABLE scanner.companies (
  company_id text PRIMARY KEY,
  first_publication_date date NOT NULL,
  selection_hash text NOT NULL,
  retrieved_through date,
  last_completed_day date,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE scanner.runs (
  run_id uuid PRIMARY KEY,
  company_id text NOT NULL REFERENCES scanner.companies(company_id),
  window_from date NOT NULL,
  window_through date NOT NULL,
  status text NOT NULL CHECK (status IN ('running','complete','incomplete','failed')),
  github_url text NOT NULL DEFAULT '',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  error text
);
CREATE TABLE scanner.publications (
  company_id text NOT NULL REFERENCES scanner.companies(company_id),
  publication_id text NOT NULL,
  fingerprint text NOT NULL,
  selection_hash text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','retry','complete')),
  attempts integer NOT NULL DEFAULT 0,
  result jsonb,
  last_error text,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, publication_id)
);
CREATE INDEX publications_pending ON scanner.publications(company_id, status, next_attempt_at);
CREATE TABLE scanner.mail_batches (
  batch_id uuid PRIMARY KEY,
  company_id text NOT NULL REFERENCES scanner.companies(company_id),
  recipient text NOT NULL,
  selection_hash text NOT NULL,
  results jsonb NOT NULL,
  status text NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared','sending','sent','cancelled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz
);
CREATE TABLE scanner.notifications (
  company_id text NOT NULL REFERENCES scanner.companies(company_id),
  publication_id text NOT NULL,
  fingerprint text NOT NULL,
  selection_hash text NOT NULL,
  result jsonb NOT NULL,
  batch_id uuid REFERENCES scanner.mail_batches(batch_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, publication_id, fingerprint)
);

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA scanner TO scanner_worker;
-- No grants to anon/authenticated; RLS also protects accidentally exposed tables.
ALTER TABLE scanner.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner.publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner.mail_batches ENABLE ROW LEVEL SECURITY;
CREATE POLICY worker ON scanner.companies TO scanner_worker USING (true) WITH CHECK (true);
CREATE POLICY worker ON scanner.runs TO scanner_worker USING (true) WITH CHECK (true);
CREATE POLICY worker ON scanner.publications TO scanner_worker USING (true) WITH CHECK (true);
CREATE POLICY worker ON scanner.notifications TO scanner_worker USING (true) WITH CHECK (true);
CREATE POLICY worker ON scanner.mail_batches TO scanner_worker USING (true) WITH CHECK (true);
COMMIT;

-- After migration, separately enable login with a strong password of your choice:
-- ALTER ROLE scanner_worker LOGIN PASSWORD '<choose-your-own-password>';
-- Never commit or paste the real password into chat or repository files.
