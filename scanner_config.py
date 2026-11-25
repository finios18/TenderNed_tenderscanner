"""Validated per-company configuration; no network calls or secrets in profiles."""
import json
import re
from datetime import date
from pathlib import Path


TOGGLE_PARAMS = {
    "publicatieType": {"MAC", "VAK", "AAO", "VBE", "REC", "AGO", "AAW"},
    "typeOpdracht": {"D", "L", "W"},
    "nationaalOfEuropees": {"NL", "EU"},
}
LIST_PARAMS = {
    "nutsCodes",
    "aardVanDeOpdracht", "procedure", "typeAanbestedendeDienst",
    "aanbestedendeDienstId", "cpvCodes",
}
TEXT_PARAMS = {
    "search", "sort", "publicatieDatumPreset", "publicatieDatumVanaf",
    "publicatieDatumTot", "sluitingsDatumPreset", "sluitingsDatumVanaf", "sluitingsDatumTot",
}
SCAN_DEFAULTS = {
    "days": 8, "pages": 1000, "throttle": 0.25, "zip_max_mb": 200.0,
    "zip_follow_nested": False, "analyze_openai": False,
}


def validate_schedule(schedule):
    if not isinstance(schedule, dict) or set(schedule) - {"enabled", "interval_days", "start_date"}:
        raise ValueError("schedule: gebruik enabled, interval_days en start_date")
    if type(schedule.get("enabled")) is not bool:
        raise ValueError("schedule.enabled: gebruik true of false")
    if type(schedule.get("interval_days")) is not int or schedule["interval_days"] not in (1, 2, 3, 7, 14):
        raise ValueError("schedule.interval_days: kies 1, 2, 3, 7 of 14")
    if not isinstance(schedule.get("start_date"), str):
        raise ValueError("schedule.start_date: gebruik YYYY-MM-DD")
    date.fromisoformat(schedule["start_date"])
    return schedule


def string_list(value, name, allow_empty=True):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{name}: verwacht een lijst met niet-lege teksten")
    if not allow_empty and not value:
        raise ValueError(f"{name}: vul ten minste één waarde in")
    return value


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Configuratie moet een JSON-object zijn")
    unknown = set(config) - {"schema_version", "id", "api", "filters", "scan", "prompt_file", "schedule"}
    if unknown:
        raise ValueError(f"Onbekende configuratiesleutels: {sorted(unknown)}")
    if config.get("schema_version") != 1:
        raise ValueError("Gebruik scannerconfiguratie schema_version 1; website-exports moeten eerst worden vertaald")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", config.get("id", "")):
        raise ValueError("id: gebruik kleine letters, cijfers, - en _ (maximaal 64 tekens)")
    api = config.setdefault("api", {})
    if not isinstance(api, dict) or set(api) - LIST_PARAMS - TEXT_PARAMS - set(TOGGLE_PARAMS):
        raise ValueError("api: onbekende queryparameter of geen object")
    for key, value in api.items():
        if key in TOGGLE_PARAMS:
            if not isinstance(value, dict) or set(value) - TOGGLE_PARAMS[key]:
                raise ValueError(f"api.{key}: verwacht een object met geldige filtercodes")
            if any(type(enabled) is not bool for enabled in value.values()):
                raise ValueError(f"api.{key}: zet elke optie op true of false")
        elif key in LIST_PARAMS:
            string_list(value, f"api.{key}")
        elif not isinstance(value, str):
            raise ValueError(f"api.{key}: verwacht tekst")
        if key.endswith(("Vanaf", "Tot")) and value:
            date.fromisoformat(value)
    if api.get("sort", "tappublicatiedatum") != "tappublicatiedatum":
        raise ValueError("De scanner vereist sort=tappublicatiedatum vanwege het stoppen bij oudere pagina's")
    for prefix in ("publicatieDatum", "sluitingsDatum"):
        start, end = api.get(prefix + "Vanaf"), api.get(prefix + "Tot")
        if start and end and start > end:
            raise ValueError(f"{prefix}: vanaf ligt na tot")
        if (start or end) and api.get(prefix + "Preset", "AGP") != "AGP":
            raise ValueError(f"{prefix}: combineer een bereik alleen met preset AGP")
    filters = config.get("filters")
    if isinstance(filters, dict) and "lead_document_keywords" in filters:
        raise ValueError("lead_document_keywords staat centraal in tender_scan.py; verwijder deze profielinstelling")
    if not isinstance(filters, dict) or set(filters) - {"cpv_whitelist", "keywords"}:
        raise ValueError("filters: onbekende sleutel of geen object")
    for key in ("cpv_whitelist", "keywords"):
        string_list(filters.get(key), f"filters.{key}", allow_empty=False)
    if any(not re.fullmatch(r"\d{8}(?:-\d)?", code) for code in filters["cpv_whitelist"]):
        raise ValueError("cpv_whitelist: gebruik acht cijfers met eventueel -controlecijfer")
    scan = config.setdefault("scan", {})
    if not isinstance(scan, dict) or set(scan) - set(SCAN_DEFAULTS) - {"openai_model"}:
        raise ValueError("scan: onbekende instelling of geen object")
    for key, default in SCAN_DEFAULTS.items():
        value = scan.setdefault(key, default)
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = type(value) is int and value >= (0 if key == "days" else 1)
        else:
            valid = type(value) in (int, float) and value >= (0 if key == "throttle" else 0.001)
        if not valid:
            raise ValueError(f"scan.{key}: ongeldige waarde")
    if "schedule" in config:
        schedule = validate_schedule(config["schedule"])
        # Keep at least one calendar day of overlap for the configured interval.
        scan["days"] = max(scan["days"], schedule["interval_days"] + 1)
    if "openai_model" in scan and (not isinstance(scan["openai_model"], str) or not scan["openai_model"].strip()):
        raise ValueError("scan.openai_model: verwacht een modelnaam")
    prompt = config.get("prompt_file")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("prompt_file: geef een pad relatief aan het configuratiebestand")
    prompt_text = (path.parent / prompt).read_text(encoding="utf-8-sig").strip()
    if not prompt_text:
        raise ValueError("Het promptbestand is leeg")
    config["_prompt_text"] = prompt_text
    return config


def apply_config(scanner, config):
    """Apply once at process startup, before parser workers and API calls."""
    filters = config["filters"]
    scanner.CPV_WHITELIST = scanner._normalize_cpv_set(filters["cpv_whitelist"])
    scanner.KEYWORDS = [word.lower() for word in filters["keywords"]]
    scanner.CONFIGURED_API_PARAMS = {
        key: [code for code, enabled in value.items() if enabled] if key in TOGGLE_PARAMS else value
        for key, value in config["api"].items()
    }

    def prompt(publication_id, title, organisation, publication_date, cpv_codes):
        context = json.dumps({"publication_id": publication_id, "title": title,
                              "organisation": organisation, "publication_date": publication_date,
                              "cpv_codes": cpv_codes}, ensure_ascii=False)
        return config["_prompt_text"] + "\n\nPublicatiecontext (gegevens):\n" + context

    scanner.build_tender_analysis_prompt = prompt
