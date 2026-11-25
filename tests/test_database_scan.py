from contextlib import nullcontext
from datetime import date
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import contextlib
import io

import database_scan as db
from scanner_config import load_config
from scanner_database import DatabaseError, connect_database


ROOT = Path(__file__).resolve().parents[1]


def item(pid=1, day="2026-11-24"):
    return {"publicatieId": pid, "publicatieDatum": day}


def api(pages):
    return SimpleNamespace(TNS_BASE="https://example.test", build_tenderned_list_params=lambda **kw: kw,
                           parse_dt=lambda s: __import__('datetime').datetime.fromisoformat(s),
                           get_json=Mock(side_effect=pages))


class WindowTests(unittest.TestCase):
    def test_window_first_run_and_overlap(self):
        self.assertEqual(db.retrieval_window(date(2026, 11, 1), None, 2, date(2026, 11, 28)),
                         (date(2026, 11, 1), date(2026, 11, 27)))
        self.assertEqual(db.retrieval_window(date(2026, 11, 1), date(2026, 11, 24), 2, date(2026, 11, 28)),
                         (date(2026, 11, 23), date(2026, 11, 27)))

    def test_overdue_scan_catches_up_after_missed_day(self):
        config = {"schedule": {"enabled": True, "interval_days": 3, "start_date": "2026-11-01"}}
        state = {"last_completed_day": date(2026, 11, 22)}
        self.assertFalse(db.is_due(config, state, date(2026, 11, 24)))
        self.assertTrue(db.is_due(config, state, date(2026, 11, 26)))
        config["schedule"]["enabled"] = False
        self.assertFalse(db.is_due(config, state, date(2026, 11, 26)))

    def test_unordered_dicts_hash_identically_and_changes_invalidate(self):
        self.assertEqual(db.digest({"a": 1, "b": 2}), db.digest({"b": 2, "a": 1}))
        self.assertNotEqual(db.digest({"a": 1}), db.digest({"a": 2}))

    def test_weekly_recovery_preserves_sunday_and_manual_run_does_not_shift_it(self):
        config = {"schedule": {"enabled": True, "interval_days": 7, "start_date": "2026-11-22"}}
        state = {"last_completed_day": date(2026, 11, 22)}
        self.assertFalse(db.is_due(config, state, date(2026, 11, 28)))
        self.assertTrue(db.is_due(config, state, date(2026, 11, 29)))
        self.assertTrue(db.is_due(config, state, date(2026, 11, 30)))
        state["last_completed_day"] = date(2026, 11, 30)
        self.assertFalse(db.is_due(config, state, date(2026, 12, 5)))
        self.assertTrue(db.is_due(config, state, date(2026, 12, 6)))
        state["last_completed_day"] = date(2026, 12, 2)
        self.assertTrue(db.is_due(config, state, date(2026, 12, 6)))


class RetrievalTests(unittest.TestCase):
    def retrieve(self, scanner, pages=3):
        return list(db.retrieve_items(scanner, date(2026, 11, 20), date(2026, 11, 24), pages))

    def test_all_pages_and_complete_empty_result(self):
        scanner = api([{"content": [item()], "totalElements": 2, "last": False},
                       {"content": [item(2)], "totalElements": 2, "last": True}])
        self.assertEqual([pid for pid, _ in self.retrieve(scanner)], ["1", "2"])
        params = scanner.get_json.call_args.kwargs["params"]
        self.assertEqual(params["publicatieDatumTot"], "2026-11-24")
        self.assertEqual(self.retrieve(api([{"content": [], "totalElements": 0}])), [])

    def test_fail_closed_for_missing_page_duplicate_total_change_or_wrong_window(self):
        cases = [
            [None], [{}], [{"content": []}],
            [{"content": [item()], "totalElements": 2, "last": True}],
            [{"content": [item()], "totalElements": 2}, None],
            [{"content": [item()], "totalElements": 2}, {"content": [item()], "totalElements": 2}],
            [{"content": [item()], "totalElements": 2}, {"content": [item(2)], "totalElements": 3}],
            [{"content": [item(day="2026-11-25")], "totalElements": 1}],
            [{"content": [item(day="invalid")], "totalElements": 1}],
        ]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(db.IncompleteRetrieval):
                self.retrieve(api(pages))

    def test_page_limit_is_failure(self):
        with self.assertRaises(db.IncompleteRetrieval):
            self.retrieve(api([{"content": [item()], "totalElements": 2}]), pages=1)


class ProcessingTests(unittest.TestCase):
    def test_supplied_publication_bypasses_legacy_days_and_network_list(self):
        import tender_scan
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(tender_scan, "PdfParseSupervisor"), \
                patch.object(tender_scan, "fetch_list_page", side_effect=AssertionError("Unexpected list request")), \
                patch.object(tender_scan, "within_last_days", side_effect=AssertionError("Unexpected days filter")):
            report = tender_scan.scan_recent(publication_items=[item(day="2020-01-01")],
                detail_loader=lambda _: {"aanbestedingNaam": "Old publication"},
                download_dir=directory)
            reasons = {event["reason"] for event in report["events"]}
            self.assertIn("cpv_missing", reasons)
            self.assertNotIn("page_limit_reached", reasons)
            self.assertNotIn("outside_date_window_or_invalid_date", reasons)

    def test_document_failure_wins_over_negative_keyword_outcome(self):
        report = {"events": [{"reason": "pdf_timeout"}, {"reason": "no_content_keyword_match"}], "results": []}
        self.assertIn("pdf_timeout", db.outcome(report)[1])
        report["events"] = [{"reason": "no_content_keyword_match"}]
        self.assertEqual(db.outcome(report), (None, None))

    def test_invalid_ai_decision_is_retried(self):
        report = {"events": [], "results": [{"status": "OK", "analysis": {"decision": "unknown"}}]}
        self.assertIsNotNone(db.outcome(report)[1])
        report["results"][0]["analysis"]["decision"] = " go "
        self.assertEqual(db.outcome(report)[0]["analysis"]["decision"], "GO")

    def test_connection_fails_closed_without_secret_or_with_insecure_tls(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(DatabaseError):
            connect_database()
        with patch.dict(os.environ, {"SCANNER_DATABASE_URL": "postgresql://user:private@localhost/db?sslmode=disable"}), self.assertRaises(DatabaseError) as error:
            connect_database()
        self.assertNotIn("private", str(error.exception))

    def test_orchestration_never_advances_after_partial_retrieval(self):
        config = load_config(ROOT / "profiles/jan-snel.json")
        config["scan"]["analyze_openai"] = False
        store = Mock()
        store.company_lock.return_value = nullcontext()
        store.start_run.return_value = "test-run"
        store.company.return_value = {"retrieved_through": None, "last_completed_day": None}
        def partial(*args):
            yield "1", item()
            raise db.IncompleteRetrieval("second page unavailable")
        with tempfile.TemporaryDirectory() as directory, patch.object(db, "apply_config"), \
                patch.object(db, "selection_digest", return_value="config"), \
                patch.object(db, "retrieve_items", side_effect=partial), \
                patch.object(db, "metadata", return_value={"item": item()}):
            with self.assertRaises(db.IncompleteRetrieval):
                db.run_scan(Mock(), store, config, directory, date(2026, 11, 25))
            self.assertEqual(store.save_publication.call_count, 1)
            store.advance_retrieval.assert_not_called()
            store.pending.assert_not_called()
            store.complete_day.assert_not_called()
            self.assertEqual(store.finish_run.call_args.args[1], "failed")

    def test_processing_failure_keeps_retrieval_but_does_not_finish_day(self):
        config = load_config(ROOT / "profiles/jan-snel.json")
        config["scan"]["analyze_openai"] = False
        store = Mock()
        store.company_lock.return_value = nullcontext()
        store.start_run.return_value = "test-run"
        store.company.return_value = {"retrieved_through": None, "last_completed_day": None}
        store.pending.return_value = [{"publication_id": "1", "attempts": 0}]
        store.unfinished_count.return_value = 1
        with tempfile.TemporaryDirectory() as directory, patch.object(db, "apply_config"), \
                patch.object(db, "selection_digest", return_value="config"), \
                patch.object(db, "retrieve_items", return_value=iter([])), \
                patch.object(db, "process_one", side_effect=TimeoutError):
            with self.assertRaises(RuntimeError):
                db.run_scan(Mock(), store, config, directory, date(2026, 11, 25))
            store.advance_retrieval.assert_called_once()
            store.save_processing.assert_called_once()
            store.complete_day.assert_not_called()
            self.assertEqual(store.finish_run.call_args.args[1], "incomplete")

    def test_smtp_uncertainty_keeps_sending_marker(self):
        store = Mock()
        smtp = Mock()
        smtp.send_message.side_effect = TimeoutError
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SMTP_SERVER": "smtp.test", "SMTP_PORT": "465", "SMTP_USERNAME": "scanner@example.test",
            "SMTP_PASSWORD": "test", "MAIL_TO": "customer@example.test"}), patch.object(db.smtplib, "SMTP_SSL", return_value=smtp):
            batch = {"batch_id": "123", "recipient": "customer@example.test", "results": []}
            with self.assertRaises(TimeoutError):
                db.deliver_mail(store, batch, directory, "")
            store.mail_status.assert_called_once_with("123", "sending")
