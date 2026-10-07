import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from go_mail_report import create_mail_report


class MailReportTests(unittest.TestCase):
    def test_readable_go_attachment_without_raw_response(self):
        results = [{"status": "OK", "publication_id": "123", "publication_title": "Data <specialisten>",
                    "organisation": "Gemeente X", "file_id": "SECRET_FILE_ID", "raw_output": "RAW_RESPONSE",
                    "analysis": {"decision": "GO", "reason_short": "Passende detachering & inhuur",
                                 "estimated_total_value_eur": 12000000, "relevant_roles_found": ["Data engineer"],
                                 "knockout_risks": ["Referentie-eis"], "summary": {"advies": "Beoordeel de referenties"}}},
                   {"status": "OK", "publication_title": "Geen match", "analysis": {"decision": "NO_GO"}},
                   {"status": "ERROR", "analysis": {"decision": "GO"}}]
        with tempfile.TemporaryDirectory() as folder:
            metadata = create_mail_report(results, folder, "https://github.com/example/repo/actions/runs/1")
            html = Path(metadata["attachments"]).read_text(encoding="utf-8")
            body = (Path(folder) / "mail_summary.txt").read_text(encoding="utf-8")
        self.assertEqual(metadata["count"], 1)
        for text in ["Data &lt;specialisten&gt;", "€ 12.000.000", "Data engineer", "Referentie-eis", "Beoordeel de referenties", "Onbekend"]:
            self.assertIn(text, html)
        for text in ["RAW_RESPONSE", "SECRET_FILE_ID", "Geen match"]:
            self.assertNotIn(text, html)
        self.assertIn("1 GO-aanbestedingen", body)
        self.assertIn("https://github.com/example/repo/actions/runs/1", body)

    def test_no_go_has_no_attachment_and_removes_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "GO-aanbestedingen.html"
            path.write_text("oude scan", encoding="utf-8")
            metadata = create_mail_report([], folder)
            self.assertEqual(metadata["attachments"], "")
            self.assertEqual(metadata["count"], 0)
            self.assertFalse(path.exists())
            self.assertIn("geen GO-aanbestedingen", (Path(folder) / "mail_summary.txt").read_text(encoding="utf-8"))

    def test_cli_exports_workflow_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "results.json"
            source.write_text(json.dumps([{"status": "OK", "analysis": {"decision": "GO"}}]), encoding="utf-8")
            outputs = Path(folder) / "github_output.txt"
            environment = dict(os.environ, GITHUB_OUTPUT=str(outputs))
            subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "go_mail_report.py"),
                            "--results", str(source), "--output_dir", folder],
                           env=environment, check=True, capture_output=True, text=True)
            text = outputs.read_text(encoding="utf-8")
            self.assertIn("subject=TenderNed: 1 GO-aanbestedingen gevonden", text)
            self.assertIn("count=1", text)
            self.assertIn("GO-aanbestedingen.html", text)
            self.assertTrue((Path(folder) / "GO-aanbestedingen.html").exists())


if __name__ == "__main__":
    unittest.main()
