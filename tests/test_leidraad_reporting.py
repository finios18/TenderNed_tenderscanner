"""Offline checks voor titelherkenning en rapportage, zonder API/dependencies."""
import ast
import contextlib
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
import time
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_scan_functions():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "tender_scan.py").read_text(encoding="utf-8"))
    names = {"AANBESTEDING_KEYWORDS", "SUPPORTING_TENDER_DOC_TERMS", "SKIP_EVENTS", "KEYWORDS"}
    functions = {"_norm_title", "leidraad_title_hits", "supporting_doc_title_hits",
                 "leidraad_score", "find_leidraad_candidates", "scan_recent", "record_skip", "looks_like_zip",
                 "try_extract_docx_text", "supported_document_type", "safe_zip_iter", "analyze_leidraad_with_openai", "_extract_json_object"}
    nodes = [node for node in tree.body if
             isinstance(node, ast.FunctionDef) and node.name in functions or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    namespace = dict(os=os, json=json, time=time, re=re, zipfile=zipfile, ET=ET, BytesIO=io.BytesIO, DAYS_BACK_DEFAULT=1,
                     OPENAI_MODEL_DEFAULT="test", PDF_PARSE_TIMEOUT_S=60,
                     OPENAI_ANALYSIS_TIMEOUT_S=180,
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

    def test_central_priority_without_penalties_and_al_fallback(self):
        ns = load_scan_functions()
        score = ns["leidraad_score"]
        self.assertEqual(ns["AANBESTEDING_KEYWORDS"][-1], "al")
        self.assertEqual(score("AL.pdf"), 1)
        self.assertEqual(score("Algemene bepalingen.pdf"), 0)
        self.assertEqual(score("Nota van inlichtingen Leidraad.pdf"), score("Leidraad.pdf"))
        self.assertEqual(score("Leidraad inleiding omschrijving AL.pdf"), score("Leidraad.pdf"))
        for term in ns["AANBESTEDING_KEYWORDS"][:-1]:
            self.assertGreater(score(term + ".docx"), score("AL.pdf"))
        candidates, _ = ns["find_leidraad_candidates"]([
            {"title": "AL.pdf"}, {"title": "toelatingsdocument.docx"}, {"title": "Aanbesteding.docx"}])
        self.assertEqual(candidates[-1]["name"], "AL.pdf")

    def test_docx_text_and_zip_support(self):
        ns = load_scan_functions()
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Data </w:t></w:r><w:r><w:t>engineer</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Detachering</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            archive.writestr("word/header1.xml", '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Koptekst</w:t></w:r></w:p></w:hdr>')
        ok, text = ns["try_extract_docx_text"](blob.getvalue())
        self.assertTrue(ok)
        for expected in ["Data engineer", "Detachering", "Koptekst"]:
            self.assertIn(expected, text)
        self.assertEqual(ns["try_extract_docx_text"](b"ongeldig"), (False, ""))
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w") as archive:
            archive.writestr("Leidraad.DOCX", blob.getvalue())
        entries = list(ns["safe_zip_iter"](outer.getvalue(), False, "", "stukken", 0))
        self.assertTrue(entries[0][3])
        self.assertFalse(entries[0][4])
        self.assertEqual(ns["supported_document_type"]("DOCX", "Leidraad"), "docx")

    def test_docx_ai_uses_extracted_text_without_file_upload(self):
        ns = load_scan_functions()
        ns["build_tender_analysis_prompt"] = Mock(return_value="Beoordeel de leidraad")
        ns["try_extract_docx_text"] = Mock(return_value=(True, "Inhuur data engineer"))
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text='{"decision": "GO"}')
        sdk = SimpleNamespace(OpenAI=Mock(return_value=client))
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {"openai": sdk}), patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            path = Path(folder) / "Toelatingsdocument.docx"
            path.write_bytes(b"PK-test")
            result = ns["analyze_leidraad_with_openai"](str(path), "123", "Titel", "Gemeente", "2026-11-19", [])
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["file_id"])
        client.files.create.assert_not_called()
        content = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertIn("Inhuur data engineer", content[1]["text"])

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
                  process_document_blob=Mock(return_value=("OK", ["python"])),
                  analyze_leidraad_with_openai=Mock(), _safe_move_publication_folder=lambda path, *args: path,
                  ams_now=Mock(return_value=Mock(isoformat=Mock(return_value="test"))))
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            ns["scan_recent"](max_pages=1, download_dir=folder, throttle_s=0, analyze_openai=True)
            report = json.loads((Path(folder) / "overgeslagen_zonder_leidraad.json").read_text(encoding="utf-8"))
            events = json.loads((Path(folder) / "overgeslagen_overzicht.json").read_text(encoding="utf-8"))["events"]
            self.assertEqual(json.loads((Path(folder) / "current_scan_results.json").read_text(encoding="utf-8")), [])
        publication = report["publications"][0]
        self.assertEqual(publication["publication_id"], "123")
        self.assertEqual(publication["title"], "Test inhuur")
        self.assertEqual([d["type"] for d in publication["documents"]], ["pdf", "xlsx"])
        self.assertIn("Tarieven.xlsx", output.getvalue())
        self.assertEqual({event["reason"] for event in events}, {"no_leidraad", "missing_download_link", "page_limit_reached"})
        self.assertEqual(next(event for event in events if event["reason"] == "missing_download_link")["document_name"], "Tarieven.xlsx")
        ns["analyze_leidraad_with_openai"].assert_not_called()
        ns["PdfParseSupervisor"].return_value.shutdown.assert_called_once()

    def test_keywords_and_api_context(self):
        ns = load_scan_functions()
        for keyword in ["detachering", "personeelsinhuur", "terbeschikkingstelling", "recruitment", "data governance", "data stewardship"]:
            self.assertIn(keyword, ns["KEYWORDS"])
        ns["record_skip"]("api_http_error", detail="HTTP 503: https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties/123/documenten")
        self.assertEqual(ns["SKIP_EVENTS"][0]["publication_id"], "123")

    def test_skip_reasons_across_scan_branches(self):
        cases = [
            ("date", "outside_date_window_or_invalid_date"),
            ("cpv", "cpv_no_match"),
            ("missing_cpv", "cpv_missing"),
            ("unsupported", "unsupported_document_type"),
            ("no_keywords", "no_content_keyword_match"),
            ("timeout", "pdf_timeout"),
            ("ai_error", "openai_analysis_failed_or_skipped"),
            ("no_go", "openai_no_go"),
            ("docx", "openai_no_go"),
            ("zip_docx", "openai_no_go"),
        ]
        for scenario, expected in cases:
            with self.subTest(scenario=scenario):
                ns = load_scan_functions()
                doc = {"documentNaam": "Leidraad.pdf", "typeDocument": {"code": "pdf"},
                       "links": {"download": {"href": "/test"}}}
                if scenario == "unsupported":
                    doc.update(documentNaam="Tarieven.xlsx", typeDocument={"code": "xlsx"})
                if scenario == "docx":
                    doc.update(documentNaam="Toelatingsdocument.docx", typeDocument={"code": "docx"})
                if scenario == "zip_docx":
                    doc.update(documentNaam="Stukken.zip", typeDocument={"code": "zip"})
                cpv = ([], set()) if scenario == "missing_cpv" else (["99999999"], {"99999999"}) if scenario == "cpv" else (["79620000"], {"79620000"})
                ns.update(log=Mock(), hr=Mock(), build_tenderned_list_params=Mock(return_value={}),
                          PdfParseSupervisor=Mock(), within_last_days=Mock(return_value=scenario != "date"),
                          fetch_list_page=Mock(return_value={"content": [{"id": 123, "datum": "2026-10-07"}]}),
                          fetch_detail=Mock(return_value={"aanbestedingNaam": "Test"}),
                          collect_all_cpv=Mock(return_value=cpv), CPV_WHITELIST={"79620000"},
                          fetch_documents=Mock(return_value=[doc]), download_bytes=Mock(return_value=b"pdf"),
                          process_document_blob=Mock(return_value=("TIMEOUT" if scenario == "timeout" else "OK",
                                                                 [] if scenario in {"no_keywords", "timeout"} else ["detachering"])),
                          analyze_leidraad_with_openai=Mock(return_value={"status": "ERROR", "error": "test"} if scenario == "ai_error" else
                                                           {"status": "OK", "analysis": {"decision": "NO_GO"}}),
                          _safe_move_publication_folder=lambda path, *args: path,
                          ams_now=Mock(return_value=Mock(isoformat=Mock(return_value="test"))))
                if scenario == "zip_docx":
                    ns["safe_zip_iter"] = Mock(return_value=[("Stukken/Leidraad.docx", "Leidraad.docx", b"PK-test", True, False)])
                with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
                    ns["scan_recent"](max_pages=1, download_dir=folder, throttle_s=0, analyze_openai=True)
                    events = json.loads((Path(folder) / "overgeslagen_overzicht.json").read_text(encoding="utf-8"))["events"]
                self.assertIn(expected, {event["reason"] for event in events})
                if scenario in {"docx", "zip_docx"}:
                    self.assertTrue(ns["analyze_leidraad_with_openai"].call_args.kwargs["pdf_path"].endswith(".docx"))
                    self.assertEqual(next(event for event in events if event["reason"] == "openai_no_go")["document_type"], "docx")
                if scenario in {"cpv", "missing_cpv"}:
                    ns["fetch_documents"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
