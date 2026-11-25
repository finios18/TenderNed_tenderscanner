"""Private PostgreSQL state. One session lock serializes all work for a company."""
from contextlib import contextmanager
import hashlib
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class DatabaseError(RuntimeError):
    pass


def connection_error_message(exc):
    """Classify locally; never print driver messages, which may contain credentials."""
    text = str(exc).lower()
    state = getattr(exc, "sqlstate", None)
    if "tenant or user not found" in text:
        return "DB_PROJECT: poolerhost en gebruikersnaam horen niet bij hetzelfde project. Kopieer de host uit Supabase Connect en gebruik scanner_worker.PROJECT_REF."
    if state == "28P01" or "password authentication failed" in text or "sasl authentication failed" in text:
        return "DB_AUTH: database weigert het wachtwoord. Gebruik het wachtwoord van scanner_worker (niet postgres) en URL-codeer speciale tekens in de URI."
    if "not permitted to log in" in text:
        return "DB_LOGIN: scanner_worker heeft nog geen LOGIN-recht; controleer ALTER ROLE scanner_worker LOGIN in Supabase."
    if "circuit breaker" in text or "too many authentication" in text:
        return "DB_AUTH_LIMIT: pooler blokkeert tijdelijk na mislukte inlogpogingen. Controleer de gegevens en wacht voordat je opnieuw test."
    if state == "53300" or "too many connections" in text or "max client connections" in text:
        return "DB_CAPACITY: database/pooler heeft te veel verbindingen; probeer later opnieuw."
    if "certificate" in text or "ssl" in text or "tls" in text:
        return "DB_TLS: de beveiligde verbinding mislukt. Controleer TLS-instellingen en bij verify-full het CA-certificaat; schakel TLS niet uit."
    if any(term in text for term in ("could not translate host", "name or service not known", "getaddrinfo", "nodename nor servname", "failed to resolve")):
        return "DB_DNS: de databasehost kan niet worden gevonden. Kopieer de exacte Session pooler-host uit Supabase Connect."
    if "timeout" in text or "timed out" in text:
        return "DB_TIMEOUT: database/pooler reageert niet op tijd. Controleer of het project actief is en of netwerkrestricties GitHub Actions toelaten."
    if any(term in text for term in ("connection refused", "network is unreachable", "no route to host", "permission denied")):
        return "DB_NETWORK: de verbinding wordt geweigerd of geblokkeerd. Controleer projectstatus, Session pooler-poort 5432 en netwerkrestricties."
    if state == "3D000" or "database" in text and "does not exist" in text:
        return "DB_NAME: de opgegeven database bestaat niet; Supabase gebruikt normaal database postgres."
    if state == "28000" or "no pg_hba.conf entry" in text:
        return "DB_ACCESS: toegang geweigerd; controleer gebruikersrol, LOGIN, TLS en netwerkrestricties."
    if any(term in text for term in ("invalid dsn", "invalid connection", "missing ", "invalid percent", "invalid integer", "invalid uri")):
        return "DB_URI: ongeldige verbindingsstring. Gebruik de volledige PostgreSQL-URI en URL-codeer het wachtwoord."
    return "DB_CONNECTION: databaseverbinding mislukt; controleer de database-/poolerlogs in Supabase voor de serveroorzaak."


def connect_database():
    dsn = os.environ.get("SCANNER_DATABASE_URL")
    if not dsn:
        raise DatabaseError("SCANNER_DATABASE_URL ontbreekt; geen terugval naar een stateloze scan")
    try:
        dsn = dsn.strip()
        if dsn.startswith(("postgresql://", "postgres://")):
            if re.search(r"%(?![0-9a-fA-F]{2})", dsn) or urlsplit(dsn).netloc.count("@") > 1:
                raise DatabaseError("DB_URI: URL-codeer speciale tekens in het wachtwoord, bijvoorbeeld @ als %40 en % als %25")
        options = conninfo_to_dict(dsn)
        if options.get("host", "").endswith(".pooler.supabase.com"):
            if not re.fullmatch(r"scanner_worker\.[a-z0-9]+", options.get("user", "")):
                raise DatabaseError("DB_USER: gebruik bij de Supabase-pooler scanner_worker.PROJECT_REF als gebruikersnaam")
            if options.get("port", "5432") != "5432":
                raise DatabaseError("DB_PORT: deze scanner vereist Session pooler op poort 5432, geen Transaction pooler")
        if options.get("sslmode", "require") not in {"require", "verify-ca", "verify-full"}:
            raise DatabaseError("Gebruik sslmode=require of verify-full voor de databaseverbinding")
        options.setdefault("sslmode", "require")
        return psycopg.connect(**options, autocommit=True, row_factory=dict_row,
                               connect_timeout=15, application_name="tenderscanner")
    except DatabaseError:
        raise
    except Exception as exc:
        # Connection strings, credentials and server error details never enter logs.
        raise DatabaseError(connection_error_message(exc)) from None


class Store:
    def __init__(self, connection):
        self.connection = connection

    def one(self, sql, params=()):
        return self.connection.execute(sql, params).fetchone()

    @contextmanager
    def company_lock(self, company_id):
        key = int.from_bytes(hashlib.sha256(("tenderscanner:" + company_id).encode()).digest()[:8], "big", signed=True)
        if not self.one("SELECT pg_try_advisory_lock(%s) AS acquired", (key,))["acquired"]:
            raise DatabaseError("Dit bedrijf heeft al een actieve database-scan")
        try:
            yield
        finally:
            if not self.connection.closed:
                self.connection.execute("SELECT pg_advisory_unlock(%s)", (key,))

    def company(self, company_id, first_date, selection_hash):
        with self.connection.transaction():
            self.connection.execute("""
                INSERT INTO scanner.companies(company_id, first_publication_date, selection_hash)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
            """, (company_id, first_date, selection_hash))
            state = self.one("SELECT * FROM scanner.companies WHERE company_id=%s FOR UPDATE", (company_id,))
            if state["selection_hash"] != selection_hash or state["first_publication_date"] != first_date:
                self.connection.execute("""
                    UPDATE scanner.companies SET selection_hash=%s, first_publication_date=%s,
                      retrieved_through=NULL, last_completed_day=NULL, updated_at=now() WHERE company_id=%s
                """, (selection_hash, first_date, company_id))
                state.update(selection_hash=selection_hash, first_publication_date=first_date,
                             retrieved_through=None, last_completed_day=None)
                print("Selectie/prompt gewijzigd: opnieuw ophalen vanaf de ingestelde eerste publicatiedatum")
            return state

    def start_run(self, company_id, start, end, github_url):
        run_id = str(uuid4())
        self.connection.execute("""UPDATE scanner.runs SET status='failed',finished_at=now(),
            error='Vorige uitvoering beëindigd zonder afsluiting' WHERE company_id=%s AND status='running'""", (company_id,))
        self.connection.execute("""
            INSERT INTO scanner.runs(run_id,company_id,window_from,window_through,status,github_url)
            VALUES (%s,%s,%s,%s,'running',%s)
        """, (run_id, company_id, start, end, github_url))
        return run_id

    def finish_run(self, run_id, status, error=None):
        self.connection.execute("UPDATE scanner.runs SET status=%s,error=%s,finished_at=now() WHERE run_id=%s",
                                (status, error, run_id))

    def save_publication(self, company_id, publication_id, fingerprint, selection_hash, payload):
        self.connection.execute("""
            INSERT INTO scanner.publications(company_id,publication_id,fingerprint,selection_hash,payload)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (company_id,publication_id) DO UPDATE SET
              payload=EXCLUDED.payload, seen_at=now(), fingerprint=EXCLUDED.fingerprint,
              selection_hash=EXCLUDED.selection_hash,
              status=CASE WHEN publications.fingerprint<>EXCLUDED.fingerprint THEN 'pending' ELSE publications.status END,
              attempts=CASE WHEN publications.fingerprint<>EXCLUDED.fingerprint THEN 0 ELSE publications.attempts END,
              result=CASE WHEN publications.fingerprint<>EXCLUDED.fingerprint THEN NULL ELSE publications.result END,
              next_attempt_at=CASE WHEN publications.fingerprint<>EXCLUDED.fingerprint THEN now() ELSE publications.next_attempt_at END
        """, (company_id, publication_id, fingerprint, selection_hash, Jsonb(payload)))

    def advance_retrieval(self, company_id, end):
        self.connection.execute("""
            UPDATE scanner.companies SET retrieved_through=GREATEST(retrieved_through,%s), updated_at=now()
            WHERE company_id=%s
        """, (end, company_id))

    def pending(self, company_id, selection_hash):
        return self.connection.execute("""
            SELECT * FROM scanner.publications
            WHERE company_id=%s AND selection_hash=%s AND status<>'complete' AND next_attempt_at<=now()
            ORDER BY publication_id
        """, (company_id, selection_hash)).fetchall()

    def save_processing(self, row, result, retry_reason=None):
        with self.connection.transaction():
            self.connection.execute("""
                UPDATE scanner.publications SET status=%s, attempts=attempts+1, result=%s, last_error=%s,
                  next_attempt_at=now()+ interval '1 hour' * LEAST(24, power(2,LEAST(attempts,5)))
                WHERE company_id=%s AND publication_id=%s AND fingerprint=%s
            """, ("retry" if retry_reason else "complete", Jsonb(result), retry_reason,
                  row["company_id"], row["publication_id"], row["fingerprint"]))
            if not retry_reason and result and result.get("analysis", {}).get("decision") == "GO":
                self.connection.execute("""
                    INSERT INTO scanner.notifications(company_id,publication_id,fingerprint,selection_hash,result)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """, (row["company_id"], row["publication_id"], row["fingerprint"], row["selection_hash"], Jsonb(result)))

    def unfinished_count(self, company_id, selection_hash):
        return self.one("""SELECT count(*) AS n FROM scanner.publications
            WHERE company_id=%s AND selection_hash=%s AND status<>'complete'""", (company_id, selection_hash))["n"]

    def complete_day(self, company_id, today):
        self.connection.execute("UPDATE scanner.companies SET last_completed_day=%s,updated_at=now() WHERE company_id=%s",
                                (today, company_id))

    def prepare_mail(self, company_id, selection_hash, recipient):
        # Never silently resend a batch whose SMTP delivery/acknowledgement is uncertain.
        if self.one("SELECT batch_id FROM scanner.mail_batches WHERE company_id=%s AND status='sending'", (company_id,)):
            raise DatabaseError("Onzekere mailaflevering: controleer scanner.mail_batches en bevestig of heropen de batch")
        with self.connection.transaction():
            stale = self.connection.execute("""SELECT b.batch_id FROM scanner.mail_batches b
                WHERE b.company_id=%s AND b.status='prepared' AND (b.selection_hash<>%s OR EXISTS (
                  SELECT 1 FROM scanner.notifications n LEFT JOIN scanner.publications p
                    ON p.company_id=n.company_id AND p.publication_id=n.publication_id
                  WHERE n.batch_id=b.batch_id AND (p.fingerprint IS DISTINCT FROM n.fingerprint OR p.status<>'complete')
                ))""", (company_id, selection_hash)).fetchall()
            for batch in stale:
                self.connection.execute("UPDATE scanner.notifications SET batch_id=NULL WHERE batch_id=%s", (batch["batch_id"],))
                self.connection.execute("UPDATE scanner.mail_batches SET status='cancelled' WHERE batch_id=%s", (batch["batch_id"],))
        previous = self.one("""SELECT * FROM scanner.mail_batches
            WHERE company_id=%s AND selection_hash=%s AND status='prepared' ORDER BY created_at LIMIT 1""",
                            (company_id, selection_hash))
        if previous:
            if previous["recipient"] != recipient:
                raise DatabaseError("Een voorbereide mail heeft een andere ontvanger; controleer deze batch eerst")
            return previous
        with self.connection.transaction():
            rows = self.connection.execute("""SELECT n.* FROM scanner.notifications n
                JOIN scanner.publications p ON p.company_id=n.company_id AND p.publication_id=n.publication_id
                    AND p.fingerprint=n.fingerprint AND p.status='complete'
                WHERE n.company_id=%s AND n.selection_hash=%s AND n.batch_id IS NULL ORDER BY n.publication_id
                FOR UPDATE OF n""", (company_id, selection_hash)).fetchall()
            batch_id = str(uuid4())
            results = [row["result"] for row in rows]
            self.connection.execute("""INSERT INTO scanner.mail_batches(batch_id,company_id,selection_hash,recipient,results)
                VALUES (%s,%s,%s,%s,%s)""", (batch_id, company_id, selection_hash, recipient, Jsonb(results)))
            for row in rows:
                self.connection.execute("""UPDATE scanner.notifications SET batch_id=%s
                    WHERE company_id=%s AND publication_id=%s AND fingerprint=%s""",
                                        (batch_id, company_id, row["publication_id"], row["fingerprint"]))
        return {"batch_id": batch_id, "recipient": recipient, "results": results}

    def mail_status(self, batch_id, status):
        self.connection.execute("""UPDATE scanner.mail_batches SET status=%s,
            sent_at=CASE WHEN %s='sent' THEN now() ELSE sent_at END WHERE batch_id=%s""", (status, status, batch_id))

    def outstanding_mail_count(self, company_id, selection_hash):
        return self.one("""SELECT count(*) AS n FROM scanner.notifications n
            JOIN scanner.publications p ON p.company_id=n.company_id AND p.publication_id=n.publication_id
                AND p.fingerprint=n.fingerprint AND p.status='complete'
            LEFT JOIN scanner.mail_batches b ON b.batch_id=n.batch_id
            WHERE n.company_id=%s AND n.selection_hash=%s AND (b.status IS NULL OR b.status<>'sent')""",
                        (company_id, selection_hash))["n"]
