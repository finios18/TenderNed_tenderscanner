"""Offline checks voor titelherkenning en rapportage, zonder API/dependencies."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock


def load_scan_functions():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "tender_scan.py").read_text(encoding="utf-8"))
    names = {"AANBESTEDING_KEYWORDS", "LEIDRAAD_TITLE_TERMS", "SUPPORTING_TENDER_DOC_TERMS"}
    functions = {"_norm_title", "leidraad_title_hits", "supporting_doc_title_hits",
                 "leidraad_score", "find_leidraad_candidates", "scan_recent"}
    nodes = [node for node in tree.body if
             isinstance(node, ast.FunctionDef) and node.name in functions or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    namespace = dict(os=os, json=json, time=time, DAYS_BACK_DEFAULT=1,
                     OPENAI_MODEL_DEFAULT="test", PDF_PARSE_TIMEOUT_S=60,
                     SLOW_STEP_S=2, VERBOSE_STEPS=False, KEYWORDS=["python"], WEB_BASE="https://example.test")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "tender_scan.py", "exec"), namespace)
    return namespace


class LeidraadTests(unittest.TestCase):
    def test_new_titles_and_priority(self):
        ns = load_scan_functions()
        for title in ["Selectiedocument.pdf", "INKOOP_DOCUMENT.pdf", "Uitnodiging tot inschrijving.pdf",
                      "BESTEK.pdf", "Tender document.pdf", "Inleiding.pdf", "omschrijving.pdf", "UTI.pdf"]:
            self.assertTrue(ns["leidraad_title_hits"](title), title)
        self.assertGreater(ns["leidraad_score"]("Aanbestedingsleidraad.pdf"), ns["leidraad_score"]("Inleiding.pdf"))

    def test_missing_leidraad_report_and_no_ai_call(self):
        ns = load_scan_functions()
        ns.update(log=Mock(), hr=Mock(), build_tenderned_list_params=Mock(return_value={}),
                  PdfParseSupervisor=Mock(), within_last_days=Mock(return_value=True),
                  fetch_list_page=Mock(return_value={"content": [{"id": 123, "datum": "2026-10-07"}]}),
                  fetch_detail=Mock(return_value={"aanbestedingNaam": "Test inhuur", "opdrachtgeverNaam": "Gemeente"}),
                  collect_all_cpv=Mock(return_value=(["79620000"], {"79620000"})),
                  CPV_WHITELIST={"79620000"}, fetch_documents=Mock(return_value=[
                      {"documentNaam": "Bijlage.pdf", "typeDocument": {"code": "pdf"},
                       "links": {"download": {"href": "/test"}}},
                      {"documentNaam": "Tarieven.xlsx", "typeDocument": {"code": "xlsx"}},
                  ]), download_bytes=Mock(return_value=b"pdf"),
                  process_pdf_blob=Mock(return_value=("OK", ["python"])),
                  analyze_leidraad_with_openai=Mock(), _safe_move_publication_folder=lambda path, *args: path,
                  ams_now=Mock(return_value=Mock(isoformat=Mock(return_value="test"))))
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            ns["scan_recent"](max_pages=1, download_dir=folder, throttle_s=0, analyze_openai=True)
            report = json.loads((Path(folder) / "overgeslagen_zonder_leidraad.json").read_text(encoding="utf-8"))
        publication = report["publications"][0]
        self.assertEqual(publication["publication_id"], "123")
        self.assertEqual(publication["title"], "Test inhuur")
        self.assertEqual([d["type"] for d in publication["documents"]], ["pdf", "xlsx"])
        self.assertIn("Tarieven.xlsx", output.getvalue())
        ns["analyze_leidraad_with_openai"].assert_not_called()
        ns["PdfParseSupervisor"].return_value.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
