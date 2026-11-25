"""Real PostgreSQL checks, only against an explicitly supplied disposable *_test database."""
import os
from pathlib import Path
from datetime import date
from uuid import uuid4
import unittest
from unittest.mock import patch
import tempfile

import psycopg
from psycopg.rows import dict_row

from scanner_database import DatabaseError, Store
import database_scan
from scanner_config import load_config


@unittest.skipUnless(os.environ.get("TEST_SCANNER_ADMIN_URL"), "Disposable PostgreSQL test database not configured")
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = psycopg.connect(os.environ["TEST_SCANNER_ADMIN_URL"], autocommit=True, row_factory=dict_row)
        if not cls.conn.info.dbname.endswith("_test"):
            cls.conn.close()
            raise RuntimeError("Integration tests require a disposable database whose name ends in _test")
        cls.conn.execute("DROP SCHEMA IF EXISTS scanner CASCADE")
        cls.conn.execute((Path(__file__).resolve().parents[1] / "database/001_scanner.sql").read_text(encoding="utf-8"))
        cls.conn.execute("SET ROLE scanner_worker")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.store = Store(self.conn)
        self.company = "test-" + uuid4().hex
        self.store.company(self.company, date(2026, 11, 1), "config1")

    def save(self, fingerprint="version1", selection="config1"):
        self.store.save_publication(self.company, "123", fingerprint, selection, {"item": {"publicatieId": "123"}})

    def test_upsert_deduplicates_and_changes_reopen(self):
        self.save()
        row = self.store.pending(self.company, "config1")[0]
        self.store.save_processing(row, {"status": "OK", "analysis": {"decision": "NO_GO"}})
        self.save()
        self.assertEqual(self.store.pending(self.company, "config1"), [])
        self.save("version2")
        self.assertEqual(len(self.store.pending(self.company, "config1")), 1)

    def test_retry_survives_and_is_backed_off(self):
        self.save()
        row = self.store.pending(self.company, "config1")[0]
        self.store.save_processing(row, None, "pdf timeout")
        self.assertEqual(self.store.unfinished_count(self.company, "config1"), 1)
        self.assertEqual(self.store.pending(self.company, "config1"), [])
        self.save()
        self.assertEqual(self.store.pending(self.company, "config1"), [])

    def test_go_mail_is_recorded_once_and_uncertain_delivery_blocks(self):
        self.save()
        row = self.store.pending(self.company, "config1")[0]
        result = {"status": "OK", "analysis": {"decision": "GO"}, "publication_id": "123"}
        self.store.save_processing(row, result)
        self.store.save_processing(row, result)
        batch = self.store.prepare_mail(self.company, "config1", "test@example.test")
        self.assertEqual(len(batch["results"]), 1)
        self.assertEqual(str(self.store.prepare_mail(self.company, "config1", "test@example.test")["batch_id"]), batch["batch_id"])
        self.store.mail_status(batch["batch_id"], "sending")
        with self.assertRaises(DatabaseError):
            self.store.prepare_mail(self.company, "config1", "test@example.test")
        self.store.mail_status(batch["batch_id"], "sent")
        self.assertEqual(self.store.outstanding_mail_count(self.company, "config1"), 0)
        self.assertEqual(self.store.prepare_mail(self.company, "config1", "test@example.test")["results"], [])

    def test_config_change_resets_retrieval_and_ignores_old_queue(self):
        self.save()
        self.store.advance_retrieval(self.company, date(2026, 11, 24))
        self.store.complete_day(self.company, date(2026, 11, 25))
        state = self.store.company(self.company, date(2026, 11, 1), "config2")
        self.assertIsNone(state["retrieved_through"])
        self.assertIsNone(state["last_completed_day"])
        self.assertEqual(self.store.pending(self.company, "config2"), [])

    def test_session_lock_prevents_two_workers(self):
        other = psycopg.connect(os.environ["TEST_SCANNER_ADMIN_URL"], autocommit=True, row_factory=dict_row)
        try:
            other.execute("SET ROLE scanner_worker")
            with self.store.company_lock(self.company):
                with self.assertRaises(DatabaseError):
                    with Store(other).company_lock(self.company):
                        self.fail("Second worker acquired lock")
            with Store(other).company_lock(self.company):
                pass
        finally:
            other.close()

    def test_company_isolation_and_worker_privileges(self):
        self.save()
        other = "test-" + uuid4().hex
        self.store.company(other, date(2026, 11, 1), "config1")
        self.assertEqual(self.store.pending(other, "config1"), [])
        rights = self.store.one("""SELECT has_schema_privilege(current_user,'scanner','CREATE') AS create_schema,
            has_table_privilege(current_user,'scanner.companies','DELETE') AS delete_rows,
            EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
              LATERAL aclexplode(c.relacl) a WHERE n.nspname='scanner' AND a.grantee=0
              AND a.privilege_type='SELECT') AS public_read""")
        self.assertFalse(any(rights.values()))

    def test_obsolete_go_is_not_mailed_after_changed_publication(self):
        self.save()
        row = self.store.pending(self.company, "config1")[0]
        self.store.save_processing(row, {"status": "OK", "analysis": {"decision": "GO"}})
        first = self.store.prepare_mail(self.company, "config1", "test@example.test")
        self.save("version2")
        row = self.store.pending(self.company, "config1")[0]
        self.store.save_processing(row, {"status": "OK", "analysis": {"decision": "NO_GO"}})
        second = self.store.prepare_mail(self.company, "config1", "test@example.test")
        self.assertEqual(second["results"], [])
        state = self.store.one("SELECT status FROM scanner.mail_batches WHERE batch_id=%s", (first["batch_id"],))
        self.assertEqual(state["status"], "cancelled")

    def test_complete_pipeline_reuses_saved_assessment_on_overlap(self):
        import tender_scan
        config = load_config(Path(__file__).resolve().parents[1] / "profiles/jan-snel.json")
        config["id"] = self.company
        config["scan"]["analyze_openai"] = False
        publication = {"publicatieId": "123", "publicatieDatum": "2026-11-24"}
        payload = {"item": publication, "detail": {"aanbestedingNaam": "Test"}, "documents": []}
        result = {"status": "OK", "analysis": {"decision": "GO"}, "publication_id": "123"}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(database_scan, "retrieve_items", side_effect=lambda *args: iter([("123", publication)])), \
                patch.object(database_scan, "metadata", return_value=payload), \
                patch.object(database_scan, "process_one", return_value={"events": [], "results": [result]}) as processing:
            for _ in range(2):
                self.assertTrue(database_scan.run_scan(tender_scan, self.store, config, directory, date(2026, 11, 25)))
            self.assertEqual(processing.call_count, 1)
            state = self.store.one("SELECT * FROM scanner.companies WHERE company_id=%s", (self.company,))
            self.assertEqual(state["retrieved_through"], date(2026, 11, 24))
            self.assertEqual(state["last_completed_day"], date(2026, 11, 25))
            self.assertEqual(self.store.outstanding_mail_count(self.company, state["selection_hash"]), 1)
