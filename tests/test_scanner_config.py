import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scanner_config
import tender_scan


ROOT = Path(__file__).resolve().parents[1]


class ScannerConfigTests(unittest.TestCase):
    def test_profiles_validate_without_network(self):
        for path in (ROOT / "profiles").glob("*.json"):
            with self.subTest(path=path):
                config = scanner_config.load_config(path)
                self.assertTrue(config["_prompt_text"])

    def test_query_and_company_prompt_are_applied(self):
        config = scanner_config.load_config(ROOT / "profiles/hob.json")
        config["api"].update(search="data", procedure=["OPE"], nutsCodes=[])
        with patch.multiple(tender_scan, CONFIGURED_API_PARAMS=None,
                            KEYWORDS=[], CPV_WHITELIST=set(), AANBESTEDING_KEYWORDS=[],
                            build_tender_analysis_prompt=tender_scan.build_tender_analysis_prompt):
            scanner_config.apply_config(tender_scan, config)
            params = tender_scan.build_tenderned_list_params(page=3, size=50)
            self.assertEqual(params["page"], 3)
            self.assertEqual(params["procedure"], ["OPE"])
            self.assertEqual(params["publicatieType"], ["VAK", "AAO", "REC"])
            self.assertEqual(tender_scan.AANBESTEDING_KEYWORDS, [])
            self.assertNotIn("nutsCodes", params)
            self.assertEqual(params["sort"], "tappublicatiedatum")
            self.assertIn("72000000", tender_scan.CPV_WHITELIST)
            prompt = tender_scan.build_tender_analysis_prompt("123", "Titel {test}", "Gemeente", "2026-11-24", [])
            self.assertIn('"publication_id": "123"', prompt)
            self.assertIn("Titel {test}", prompt)

    def test_invalid_config_fails_before_scan(self):
        base = json.loads((ROOT / "profiles/hob.json").read_text(encoding="utf-8"))
        base["prompt_file"] = str(ROOT / "prompts/hob.txt")
        cases = [lambda c: c["api"].update(zoekterm="ignored"),
                 lambda c: c["api"].update(sort="relevantie"),
                 lambda c: c["api"].update(typeOpdracht=["X"]),
                 lambda c: c["api"].update(typeOpdracht={"X": True}),
                 lambda c: c["api"].update(typeOpdracht={"D": "false"}),
                 lambda c: c["filters"].update(lead_document_keywords=["bestek"]),
                 lambda c: c["api"].update(publicatieType="AAO"),
                 lambda c: c["filters"].update(keywords=[]),
                 lambda c: c["filters"].update(cpv_whitelist=["720"]),
                 lambda c: c["scan"].update(analyze_openai="false"),
                 lambda c: c["scan"].update(pages=0),
                 lambda c: c["api"].update(publicatieDatumVanaf="2026-12-01", publicatieDatumTot="2026-01-01")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for mutate in cases:
                config = copy.deepcopy(base)
                mutate(config)
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(ValueError):
                    scanner_config.load_config(path)

    def test_all_false_omits_filter_and_false_codes_are_not_added(self):
        config = scanner_config.load_config(ROOT / "profiles/hob.json")
        config["api"]["typeOpdracht"] = {"D": False, "L": False, "W": False}
        config["api"]["publicatieType"] = {"AAO": True, "VBE": False, "AGO": False}
        original_titles = tender_scan.AANBESTEDING_KEYWORDS
        with patch.multiple(tender_scan, CONFIGURED_API_PARAMS=None,
                            KEYWORDS=[], CPV_WHITELIST=set(),
                            build_tender_analysis_prompt=tender_scan.build_tender_analysis_prompt):
            scanner_config.apply_config(tender_scan, config)
            params = tender_scan.build_tenderned_list_params()
            self.assertNotIn("typeOpdracht", params)
            self.assertEqual(params["publicatieType"], ["AAO"])
            self.assertIs(tender_scan.AANBESTEDING_KEYWORDS, original_titles)
