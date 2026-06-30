 #!/usr/bin/env python3
# Laatste N dagen → filter op CPV (uit list+detail) → documenten downloaden/lezen:
# - losse PDF's direct
# - ZIP-bestanden: alle PDF's erin
# → keywords checken
# → alleen bij keyword-hits: leidraad-document identificeren op titel

import sys, os, time, argparse
from io import BytesIO
from datetime import datetime, timedelta
from dateutil.tz import gettz
from dateutil import parser as dtp
import requests
import zipfile
import json
import shutil

# Robustness / timeboxing
import multiprocessing as mp
from dataclasses import dataclass
from typing import Optional, Tuple

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TNS_BASE = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
WEB_BASE = "https://www.tenderned.nl"
HEADERS  = {"User-Agent": "tenderned-cpv-key/0.5 (+cli-zip)"}

# ==== Robustness settings ====
# Netwerk: we willen nooit onbepaald wachten; per netwerk-operatie max ~60s.
NET_TIMEOUT_S = 60
CONNECT_TIMEOUT_S = 10

# Parsing: harde cap per PDF.
PDF_PARSE_TIMEOUT_S = 60

# Logging/diagnostics
SLOW_STEP_S = 2.0          # log extra detail als een stap langer duurt dan dit
VERBOSE_STEPS = True       # zet op False als je output te noisy wordt


def _ts() -> str:
    return datetime.now(gettz("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"{_ts()} {msg}")


def _fmt_dur(seconds: float) -> str:
    return f"{seconds:.1f}s" if seconds >= 1 else f"{seconds*1000:.0f}ms"


def _build_session() -> requests.Session:
    """Requests Session met retries + backoff. Dit voorkomt veel random ConnectionReset/502/503 issues."""
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


SESSION = _build_session()

# ==== Instellingen ====
DAYS_BACK_DEFAULT = 1

# ==== TenderNed publicatiefilters ====
# Zet per optie True/False.
# True  = meenemen in de TenderNed API-query
# False = uitsluiten
#
# Let op:
# - Als binnen een filter alles op False staat, wordt dat filter NIET meegestuurd.
#   Dan laat je TenderNed dus alle opties binnen dat filter teruggeven.
# - Deze filters gebeuren server-side bij TenderNed, dus vóór document-downloads en PDF-parsing.

PUBLICATIE_TYPE_FILTERS = {
    "MAC": False,  # Marktconsultatie
    "VAK": True,   # Vooraankondiging
    "AAO": True,   # Aankondiging van de opdracht
    "REC": True,   # Rectificatie
    "AGO": False,  # Aankondiging van de gegunde opdracht
    "AAW": False,  # Aankondiging van een wijziging
}

TYPE_OPDRACHT_FILTERS = {
    "D": True,     # Diensten
    "L": True,    # Leveringen
    "W": False,    # Werken
}

NATIONAAL_OF_EUROPEES_FILTERS = {
    "NL": True,    # Nationaal
    "EU": True,    # Europees
}


def active_filter_codes(filter_dict):
    """Return alle codes die op True staan."""
    return [code for code, enabled in filter_dict.items() if enabled]


def build_tenderned_list_params(page=0, size=50):
    """Bouw query parameters voor de TenderNed lijst-endpoint.

    De drie filterblokken hierboven worden hier vertaald naar API-parameters.
    Als een filterblok geen actieve opties heeft, sturen we die parameter niet mee.
    """
    params = {
        "page": page,
        "size": size,
    }

    publicatie_types = active_filter_codes(PUBLICATIE_TYPE_FILTERS)
    type_opdrachten = active_filter_codes(TYPE_OPDRACHT_FILTERS)
    nationaal_of_europees = active_filter_codes(NATIONAAL_OF_EUROPEES_FILTERS)

    if publicatie_types:
        params["publicatieType"] = publicatie_types

    if type_opdrachten:
        params["typeOpdracht"] = type_opdrachten

    if nationaal_of_europees:
        params["nationaalOfEuropees"] = nationaal_of_europees

    return params

# Keywords voor IT / data detachering
KEYWORDS = [
    "data engineer",
    "data scientist",
    "data architect",
    "power-bi",
    "powerbi",
    "power bi",
    "azure",
    "aws",
    "python",
    "devops",
    "software developer",
    "it architect",
    "data-specialist",
    "data-engineering",
    "data-analyse",
    "data-science",
    "busines analist",
    "business analyst",
    "proces analist",
    "procesanalist",
    "proces manager",
    "procesmanager",
]

# Documenttitels die waarschijnlijk de hoofdleidraad / het beschrijvend document aanduiden.
# Matching is case-insensitive: titel/bestandsnaam wordt eerst naar lowercase gezet.
LEIDRAAD_TITLE_TERMS = [
    "beschrijvend document",
    "leidraad",
    "inschrijfleidraad",
    "inschrijf leidraad",
    "aanbestedingsdocument",
    "aanbestedings document",
    "aanbestedingsleidraad",
    "aanbestedings leidraad",
    "offerteaanvraag",
    "offerte aanvraag"
]

# Termen die iets minder hard zijn, maar vaak wel wijzen op inhoudelijk relevante stukken.
# Deze sturen we standaard nog niet naar OpenAI, maar we rapporteren ze wel als kandidaten.
SUPPORTING_TENDER_DOC_TERMS = [
    "programma van eisen",
    "pve"
]



# ==== OpenAI analyse settings ====
# Veiligheid/kosten: OpenAI-analyse staat standaard UIT.
# Gebruik: python script.py --analyze_openai
OPENAI_MODEL_DEFAULT = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_ANALYSIS_TIMEOUT_S = 180


def build_tender_analysis_prompt(publication_id: str, title: str, organisation: str, publication_date: str, cpv_codes):
    """Prompt voor strenge GO/MAYBE/NO_GO beoordeling van één leidraad."""
    cpv_text = ", ".join(cpv_codes or []) if cpv_codes else "onbekend"
    return f"""
Je analyseert een Nederlandse aanbestedingsleidraad voor een detacheerorganisatie.

Context aanbesteding:
- Publicatie-ID: {publication_id}
- Titel: {title or 'onbekend'}
- Aanbestedende dienst/opdrachtgever: {organisation or 'onbekend'}
- Publicatiedatum: {publication_date or 'onbekend'}
- CPV-codes: {cpv_text}

Bedrijfsprofiel / commerciële zoekrichting:
Wij zijn een detacheerorganisatie. Wij zoeken aanbestedingen waarbij wij professionals kunnen leveren, bemiddelen, preselecteren, contractueel/administratief afhandelen en/of ter beschikking stellen aan een opdrachtgever.

Onze primaire domeinen/functies zijn:
- Data Analyse
- Data Science
- Data Engineering
- Data Governance / Data Stewardship
- Data Architectuur / Technische data-specialisten
- AI / Advanced analytics
- Informatieanalyse
- Business Analyse
- Business Consultancy
- Procesmanagement
- Softwareontwikkeling

Daarnaast zijn breder geformuleerde inhuur- of detacheringsaanbestedingen óók interessant wanneer zij expliciet ruimte bieden voor het leveren van professionals via detachering, flexibele personeelsinhuur, recruitment, werving & selectie, ZZP-bemiddeling of raamovereenkomsten. Het document hoeft dan niet altijd expliciet één van onze primaire domeinen te noemen; een brede personeelsinhuur-raamovereenkomst kan alsnog een commerciële GO zijn.

Commerciële grens:
- GO is alleen mogelijk als de totale maximale opdrachtwaarde duidelijk maximaal EUR 80.000.000 is, óf als geen waarde wordt gevonden maar de opdracht qua aard duidelijk een passende detacherings-/inhuurraamovereenkomst is.
- NO_GO op waarde alleen wanneer het document expliciet vermeldt dat de totale maximale waarde boven EUR 80.000.000 ligt.
- Als de waarde onbekend is, gebruik value_within_80000000 = null en beoordeel de opdracht niet negatief uitsluitend door ontbrekende waarde.

Beslisregels:
Geef GO wanneer de kern van de opdracht voldoet aan ALLE onderstaande voorwaarden:
1. Het gaat primair om detachering, flexibele personeelsinhuur, tijdelijke inhuur, terbeschikkingstelling van professionals/kandidaten, recruitment/bemiddeling, brokerachtige dienstverlening, minicompetities of een raamovereenkomst voor dergelijke inzet.
2. De gevraagde dienstverlening past bij een detacheerder: kandidaten werven, selecteren, aanbieden, inzetten, begeleiden en/of contractueel/administratief afhandelen.
3. De opdracht valt binnen onze primaire domeinen.
4. Er is geen harde knock-out eis gevonden die een normale detacheerder evident uitsluit.
5. De totale maximale waarde is niet expliciet hoger dan EUR 80.000.000.

Geef MAYBE alleen wanneer er echte beslisinformatie ontbreekt of conflicteert, bijvoorbeeld:
- het is onduidelijk of het om personele inzet of een resultaat/project gaat;
- het is onduidelijk of onze domeinen of brede detacheringsdienstverlening binnen scope vallen;
- er zijn mogelijke, maar niet zekere, knock-out risico’s;
- de waarde lijkt mogelijk boven de grens te liggen maar is niet hard vast te stellen.

Geef NO_GO alleen wanneer er een harde uitsluitende reden is, bijvoorbeeld:
- het document gaat primair over softwarebouw, hardware, licenties, producten, beheer of een eindresultaat zonder passende personele inzet;
- de opdracht valt duidelijk buiten detachering/inhuur én buiten onze domeinen;
- de totale maximale waarde is expliciet hoger dan EUR 80.000.000;
- een knock-out eis sluit een detacheerder evident uit.

Belangrijke interpretatie-instructie:
Wees streng op echte afwijzingsredenen, maar niet op ontbrekende details. Een passende raamovereenkomst voor data-specialisten of flexibele personeelsinhuur hoort een GO te krijgen, tenzij je een expliciete harde reden vindt voor MAYBE of NO_GO. Ga dus niet lafjes MAYBE roepen omdat het document niet elk detail op een presenteerblaadje zet; dat is geen analyse, dat is administratieve schuilkelderpolitiek.

Baseer je oordeel alleen op de inhoud van het document. Als informatie niet gevonden wordt, gebruik null of "onbekend". Vermeld in knockout_risks alleen risico’s die echt uit het document blijken; zet daar geen generieke aanbestedingsrisico’s in.

Retourneer uitsluitend geldige JSON, zonder markdown, volgens exact deze structuur:
{{
  "decision": "GO | MAYBE | NO_GO",
  "confidence": 0,
  "reason_short": "korte conclusie in 1-2 zinnen",
  "is_detachering_or_inhuur": true,
  "relevant_roles_found": [],
  "estimated_total_value_eur": null,
  "value_within_80000000": null,
  "contract_type": "raamovereenkomst | DAS/DPS | project | broker | onbekend",
  "client": "",
  "submission_deadline": null,
  "contract_duration": null,
  "number_of_suppliers": null,
  "main_scope": "",
  "knockout_risks": [],
  "commercial_fit": "",
  "why_interesting": [],
  "why_not_interesting": [],
  "summary": {{
    "opdracht": "",
    "scope": "",
    "belangrijkste_eisen": [],
    "beoordeling_en_gunning": "",
    "planning": "",
    "advies": ""
  }}
}}
""".strip()


def _extract_json_object(text: str):
    """Best-effort JSON parser: accepteert zuivere JSON of tekst met een JSON-object erin."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


def analyze_leidraad_with_openai(pdf_path: str, publication_id: str, title: str, organisation: str,
                                  publication_date: str, cpv_codes, model: str = OPENAI_MODEL_DEFAULT,
                                  output_dir: str = None):
    """Upload één leidraad-PDF naar OpenAI en vraag een strenge JSON-analyse terug.

    Vereisten:
    - pip install openai
    - env var OPENAI_API_KEY moet gezet zijn

    Return dict met status, eventueel analysis/error/output_path.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return {"status": "SKIPPED", "error": f"PDF bestaat niet: {pdf_path}"}

    if not os.environ.get("OPENAI_API_KEY"):
        return {"status": "SKIPPED", "error": "OPENAI_API_KEY ontbreekt; OpenAI-analyse overgeslagen"}

    try:
        from openai import OpenAI
    except Exception as e:
        return {"status": "SKIPPED", "error": f"openai package niet geïnstalleerd of niet importeerbaar: {e}"}

    client = OpenAI(timeout=OPENAI_ANALYSIS_TIMEOUT_S)
    prompt = build_tender_analysis_prompt(publication_id, title, organisation, publication_date, cpv_codes)

    try:
        with open(pdf_path, "rb") as f:
            uploaded = client.files.create(file=f, purpose="assistants")

        response = client.responses.create(
            model=model,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_file", "file_id": uploaded.id},
                ],
            }],
        )

        raw_text = getattr(response, "output_text", "") or ""
        parsed = _extract_json_object(raw_text)
        result = {
            "status": "OK" if parsed is not None else "PARSE_FAIL",
            "publication_id": publication_id,
            "publication_title": title,
            "organisation": organisation,
            "leidraad_path": pdf_path,
            "model": model,
            "file_id": uploaded.id,
            "analysis": parsed,
            "raw_output": raw_text,
        }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, f"openai_analysis_{publication_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            result["output_path"] = out_path

        return result

    except Exception as e:
        return {"status": "ERROR", "error": str(e), "publication_id": publication_id, "leidraad_path": pdf_path}


# CPV whitelist voor IT / data services + personeel/inhuur
CPV_WHITELIST_RAW = [

    # --- IT / software / data services ---
    "72000000",  # IT services: consulting, software development, Internet and support
    "72100000",  # Hardware consultancy services
    "72200000",  # Software programming and consultancy services
    "72210000",  # Programming services of packaged software products
    "72220000",  # Systems and technical consultancy services
    "72221000",  # Business analysis consultancy services
    "72230000",  # Custom software development services
    "72240000",  # Systems analysis and programming services
    "72250000",  # System and support services
    "72260000",  # Software-related services
    "72263000",  # Software implementation services

    # --- Data services ---
    "72300000",  # Data services
    "72310000",  # Data processing services
    "72320000",  # Database services

    # --- R&D / consultancy (komt vaak voor bij digitale projecten) ---
    "73000000",  # Research and development services and related consultancy services
    "79000000",  # Business services: law, marketing, consulting, recruitment, printing and security
    "79410000",  # Business and management consultancy services

    # --- Personeel / detachering ---
    "79600000",  # Recruitment services
    "79610000",  # Placement services of personnel
    "79611000",  # Job search services
    "79612000",  # Placement services of office-support personnel
    "79620000",  # Supply services of personnel including temporary staff
    "79621000",  # Supply services of office personnel
    "79330000-6", # statistische dienstverlening
    "75131100-4", # Algemene personeelsdiensten voor de overheid

]

# ==== Helpers: HTTP ====
def _timeout_tuple(deadline_s: float) -> Tuple[float, float]:
    """Maak (connect, read) timeout tuple die nooit voorbij de deadline gaat."""
    remaining = max(0.1, deadline_s - time.monotonic())
    connect = min(float(CONNECT_TIMEOUT_S), remaining)
    read = max(0.1, remaining)
    return (connect, read)


def get_json(url, params=None, max_seconds: int = NET_TIMEOUT_S):
    """Robuust JSON ophalen: 404 -> None, andere errors -> None.
    Belangrijk: we begrenzen de totale tijd per call (incl. retries/backoff) op ~max_seconds.
    """
    deadline = time.monotonic() + float(max_seconds)
    attempt = 0
    while True:
        attempt += 1
        t0 = time.monotonic()
        try:
            r = SESSION.get(url, params=params, headers=HEADERS, timeout=_timeout_tuple(deadline))
            status = r.status_code

            if status == 404:
                log(f"[HTTP 404] {url} → publicatie niet gevonden, wordt overgeslagen")
                return None

            # Bij 4xx/5xx die niet 404 zijn: niet hard crashen.
            if status >= 400:
                if time.monotonic() - t0 >= SLOW_STEP_S or VERBOSE_STEPS:
                    log(f"[HTTP {status}] {url} (attempt {attempt})")
                # Laat session-retries/backoff hun werk doen; we proberen opnieuw zolang we tijd over hebben.
                if time.monotonic() >= deadline:
                    log(f"[NET TIMEOUT] {url} → >{max_seconds}s, JSON wordt overgeslagen")
                    return None
                continue

            try:
                data = r.json()
            except ValueError:
                log(f"[JSON PARSE FAIL] {url} → response is geen geldige JSON")
                return None

            dur = time.monotonic() - t0
            if dur >= SLOW_STEP_S and VERBOSE_STEPS:
                log(f"[SLOW JSON] {_fmt_dur(dur)} {url}")
            return data

        except requests.exceptions.RequestException as e:
            dur = time.monotonic() - t0
            if time.monotonic() >= deadline:
                log(f"[NET TIMEOUT] {url} → >{max_seconds}s, laatste error: {e}")
                return None
            # kort loggen, dan opnieuw proberen zolang deadline niet overschreden is
            if dur >= SLOW_STEP_S or VERBOSE_STEPS:
                log(f"[NET ERROR] {url} (attempt {attempt}) → {e}")
            continue


def fetch_list_page(page=0, size=50):
    params = build_tenderned_list_params(page=page, size=size)
    return get_json(TNS_BASE, params=params) or {}

def fetch_detail(pub_id):
    return get_json(f"{TNS_BASE}/{pub_id}") or {}

def fetch_documents(pub_id):
    data = get_json(f"{TNS_BASE}/{pub_id}/documenten") or {}
    if isinstance(data, dict):
        return data.get("documenten") or []
    if isinstance(data, list):
        return data
    return []

def download_bytes(href, timeout=120):
    """Download bytes met harde tijdslimiet. Errors leveren een Exception op die de caller afvangt.
    We loggen daarnaast slow downloads, zodat je ziet waar het 'hangt'.
    """
    url = href if href.startswith("http") else WEB_BASE + href
    deadline = time.monotonic() + float(min(int(timeout), NET_TIMEOUT_S))
    t0 = time.monotonic()
    r = SESSION.get(url, headers=HEADERS, timeout=_timeout_tuple(deadline))
    status = r.status_code
    if status == 404:
        raise requests.exceptions.HTTPError(f"404 Not Found for url: {url}", response=r)
    if status >= 400:
        raise requests.exceptions.HTTPError(f"HTTP {status} for url: {url}", response=r)
    blob = r.content
    dur = time.monotonic() - t0
    if dur >= SLOW_STEP_S and VERBOSE_STEPS:
        log(f"[SLOW DL] {_fmt_dur(dur)} {url} ({len(blob)/1024:.0f} KB)")
    return blob

# ==== Helpers: tijd / parsing ====
def parse_dt(s):
    if not s: return None
    try:
        return dtp.parse(s)
    except Exception:
        return None

def ams_now():
    return datetime.now(gettz("Europe/Amsterdam"))

def within_last_days(date_str, days_back=DAYS_BACK_DEFAULT):
    """True als publicatieDatum binnen [today-days_back, today] op datum-niveau (Europe/Amsterdam)."""
    if not date_str:
        return False
    dt = parse_dt(date_str)
    if not dt:
        return False
    d = dt.date()
    today = ams_now().date()
    cutoff = today - timedelta(days=days_back)
    return d >= cutoff

# ==== Helpers: CPV ====
def _normalize_cpv_set(raw_list):
    """Neem strings, haal zowel volledige code als basis (voor '-') op in een set."""
    out = set()
    for code in raw_list:
        if not code: continue
        c = code.strip()
        out.add(c)
        out.add(c.split("-")[0])
    return out

def _extract_cpv_codes(raw):
    """Trek CPV codes uit list/dict-structuren van de API."""
    vals = []
    if not raw:
        return []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                vals.append(x)
            elif isinstance(x, dict):
                v = x.get("code") or x.get("cpvCode") or x.get("value")
                if isinstance(v, str):
                    vals.append(v)
    elif isinstance(raw, dict):
        v = raw.get("code") or raw.get("cpvCode") or raw.get("value")
        if isinstance(v, str):
            vals.append(v)
    return vals

def collect_all_cpv(info_list: dict, info_detail: dict):
    """Combineer CPV uit lijst + detail, geef:
       - cpv_all_display: gesorteerde lijst van unieke 'volle' codes (zonder basiscodes dupliceren)
       - cpv_all_match:   set met zowel volle als basis-codes (voor matching/whitelist)"""
    list_codes   = _extract_cpv_codes((info_list or {}).get("cpvCodes"))
    detail_codes = _extract_cpv_codes((info_detail or {}).get("cpvCodes"))
    full_codes = sorted(set(list_codes + detail_codes))  # “mooie” weergave
    match_set  = _normalize_cpv_set(full_codes)          # voor whitelist-match
    return full_codes, match_set

CPV_WHITELIST = _normalize_cpv_set(CPV_WHITELIST_RAW)

# ==== Helpers: leidraad-detectie ====
def _norm_title(s: str) -> str:
    """Normaliseer documentnaam/titel voor robuuste matching."""
    return " ".join((s or "").lower().replace("_", " ").replace("-", " ").split())

def leidraad_title_hits(title: str):
    """Return lijst met leidraad-termen die in de lowercased documenttitel voorkomen."""
    normalized = _norm_title(title)
    return [term for term in LEIDRAAD_TITLE_TERMS if term in normalized]

def supporting_doc_title_hits(title: str):
    """Return lijst met aanvullende tender-documenttermen die in de titel voorkomen."""
    normalized = _norm_title(title)
    return [term for term in SUPPORTING_TENDER_DOC_TERMS if term in normalized]

def is_probable_leidraad_title(title: str) -> bool:
    return bool(leidraad_title_hits(title))

def leidraad_score(title: str) -> int:
    """Score om de beste leidraad-kandidaat te kiezen als er meerdere matches zijn."""
    normalized = _norm_title(title)
    score = 0
    # Specifieke termen zijn waardevoller dan generieke 'leidraad'.
    weighted_terms = {
        "aanbestedingsleidraad": 100,
        "aanbestedings leidraad": 100,
        "inschrijfleidraad": 95,
        "inschrijf leidraad": 95,
        "leidraad": 95,
        "aanbestedingsdocument": 90,
        "aanbestedings document": 90,
        "beschrijvend document": 85,
        "offerteaanvraag": 80,
        "offerte aanvraag": 80,
    }
    for term, weight in weighted_terms.items():
        if term in normalized:
            score += weight
    # Vermijd dat nota's of antwoorden per ongeluk als leidraad gekozen worden.
    negative_terms = ["nota van inlichtingen", "nvi", "vragen", "antwoord", "rectificatie"]
    for term in negative_terms:
        if term in normalized:
            score -= 60
    return score


def find_leidraad_candidates(downloaded_documents):
    """Zoek leidraad-kandidaten in reeds gedownloade documenten.

    Belangrijk voor de pipeline:
    deze functie wordt pas aangeroepen nadat een aanbesteding door de keyword-filter heen is.
    Matching gebeurt case-insensitive via _norm_title().
    """
    candidates = []
    supporting = []

    for doc in downloaded_documents:
        title = doc.get("title") or doc.get("filename") or ""
        l_hits = leidraad_title_hits(title)
        s_hits = supporting_doc_title_hits(title)

        if l_hits:
            candidates.append({
                "name": title,
                "path": doc.get("path", ""),
                "source": doc.get("source", ""),
                "score": leidraad_score(title),
                "title_hits": l_hits,
                "keyword_hits": doc.get("keyword_hits", []),
                "read_status": doc.get("read_status", ""),
            })
        elif s_hits:
            supporting.append({
                "name": title,
                "path": doc.get("path", ""),
                "source": doc.get("source", ""),
                "title_hits": s_hits,
                "keyword_hits": doc.get("keyword_hits", []),
                "read_status": doc.get("read_status", ""),
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates, supporting

# ==== Helpers: PDF / keywords ====
def try_extract_pdf_text(blob: bytes):
    # 1. Probeer eerst PyPDF2 (sneller / simpeler)
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(BytesIO(blob))
        chunks = []
        for p in reader.pages:
            try:
                chunks.append(p.extract_text() or "")
            except Exception:
                pass
        txt = "\n".join(chunks)
        if txt.strip():
            return True, txt
    except Exception:
        pass

    # 2. Dan pas pdfminer (duur / potentieel traag)
    try:
        from pdfminer.high_level import extract_text
        txt = extract_text(BytesIO(blob)) or ""
        return True, txt
    except Exception:
        return False, ""


def _pdf_worker_loop(in_q: mp.Queue, out_q: mp.Queue):
    """Worker-process die seriëel PDF-bytes ontvangt en text extractie uitvoert.
    We houden dit proces persistent om overhead laag te houden bij duizenden PDFs.
    """
    while True:
        item = in_q.get()
        if item is None:
            break
        job_id, label, pdf_bytes = item
        try:
            ok, text = try_extract_pdf_text(pdf_bytes)
            out_q.put((job_id, ok, text, False, label))
        except Exception:
            out_q.put((job_id, False, "", False, label))


@dataclass
class PdfParseSupervisor:
    """Superviseert 1 worker-process. Als parsing > timeout_s hangt:
    terminate + respawn, en caller krijgt direct een timeout-result terug.
    """

    timeout_s: int = PDF_PARSE_TIMEOUT_S

    def __post_init__(self):
        self._ctx = mp.get_context("spawn")  # Windows-safe
        self._in_q: Optional[mp.Queue] = None
        self._out_q: Optional[mp.Queue] = None
        self._p: Optional[mp.Process] = None
        self._job_id: int = 0
        self._start_worker()

    def _start_worker(self):
        self._in_q = self._ctx.Queue(maxsize=1)
        self._out_q = self._ctx.Queue(maxsize=1)
        self._p = self._ctx.Process(target=_pdf_worker_loop, args=(self._in_q, self._out_q), daemon=True)
        self._p.start()

    def _kill_worker(self):
        if self._p and self._p.is_alive():
            self._p.terminate()
            self._p.join(timeout=2)
        self._p = None
        self._in_q = None
        self._out_q = None

    def shutdown(self):
        try:
            if self._in_q:
                self._in_q.put(None)
        except Exception:
            pass
        self._kill_worker()

    def parse(self, pdf_bytes: bytes, label: str = "") -> Tuple[bool, str, bool]:
        """Return: (ok, text, timed_out). timed_out=True => parsing > timeout, worker is herstart."""
        if not self._p or not self._p.is_alive():
            self._kill_worker()
            self._start_worker()

        self._job_id += 1
        job_id = self._job_id

        self._in_q.put((job_id, label, pdf_bytes))

        try:
            got_job_id, ok, text, _timed_out, got_label = self._out_q.get(timeout=float(self.timeout_s))
            if got_job_id != job_id:
                # seriële modus: dit hoort niet te gebeuren; fail-safe
                return False, "", False
            return ok, text, False
        except Exception:
            # timeout of queue error -> worker hangt
            log(f"[PDF TIMEOUT] >{self.timeout_s}s tijdens parsen → worker herstart. ({label})")
            self._kill_worker()
            self._start_worker()
            return False, "", True

def keyword_hits(text: str, keywords):
    t = (text or "").lower()
    return [kw for kw in keywords if kw.lower() in t]

def hr():
    print("-" * 100)

# ==== ZIP support ====
def looks_like_zip(dtype: str, name: str) -> bool:
    if dtype and dtype.lower() == "zip":
        return True
    if name and name.lower().endswith(".zip"):
        return True
    return False

def safe_zip_iter(zip_blob: bytes, follow_nested: bool, base_outdir: str, parent_label: str, throttle_s: float):
    """
    Leest ZIP uit bytes en yield tuples van:
    (entry_label, entry_filename, entry_bytes, entry_is_pdf, entry_is_zip)

    - Slaat directories en verborgen/macOS troep over.
    - Volgt nested zip enkel als follow_nested=True.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(zip_blob))
    except zipfile.BadZipFile:
        print(f"       [ZIP] {parent_label} → onleesbare/defecte zip (BadZipFile)")
        return
    except Exception as e:
        print(f"       [ZIP] {parent_label} → zip openen FAIL: {e}")
        return

    for zi in zf.infolist():
        # Skip directories
        if zi.is_dir():
            continue
        # Skip resource forks etc.
        if os.path.basename(zi.filename).startswith("__MACOSX"):
            continue

        try:
            data = zf.read(zi)
        except RuntimeError as e:
            # password-protected or encrypted
            print(f"       [ZIP] {zi.filename} → niet leesbaar (mogelijk encrypted): {e}")
            continue
        except Exception as e:
            print(f"       [ZIP] {zi.filename} → lezen FAIL: {e}")
            continue

        fname = os.path.basename(zi.filename)
        is_pdf = fname.lower().endswith(".pdf")
        is_zip = fname.lower().endswith(".zip")
        label  = f"{parent_label}/{fname}" if parent_label else fname
        yield (label, fname, data, is_pdf, is_zip)

        time.sleep(throttle_s)

        # nested?
        if is_zip and follow_nested:
            for nested in safe_zip_iter(data, follow_nested, base_outdir, label, throttle_s):
                yield nested

def process_pdf_blob(pdf_bytes: bytes, save_as_path: str, pdf_parser: PdfParseSupervisor, label: str = ""):
    """Slaat PDF op en zoekt keywords.

    Robuustheid:
    - Parsing is timeboxed via PdfParseSupervisor (max 60s).
    - Return status: OK | FAIL | TIMEOUT
    """
    with open(save_as_path, "wb") as f:
        f.write(pdf_bytes)

    t0 = time.monotonic()
    ok_read, text, timed_out = pdf_parser.parse(pdf_bytes, label=label)
    dur = time.monotonic() - t0

    if dur >= SLOW_STEP_S and VERBOSE_STEPS:
        log(f"[SLOW PARSE] {_fmt_dur(dur)} {label}")

    if timed_out:
        return "TIMEOUT", []
    if ok_read:
        hits = keyword_hits(text, KEYWORDS)
        return "OK", hits
    return "FAIL", []


# ==== Helpers: output folders ====
def _safe_move_publication_folder(current_outdir: str, download_dir: str, pid, category: str) -> str:
    """Verplaats de map van één publicatie naar recent_downloads/GO of recent_downloads/Overig.

    Als er al een map met hetzelfde publicatie-ID bestaat, maken we een unieke suffix.
    Returnt het nieuwe pad. Bij fout blijft het oude pad leidend.
    """
    if not current_outdir or not os.path.isdir(current_outdir):
        return current_outdir

    category_root = os.path.join(download_dir, category)
    os.makedirs(category_root, exist_ok=True)

    base_name = str(pid)
    target = os.path.join(category_root, base_name)

    if os.path.abspath(current_outdir) == os.path.abspath(target):
        return target

    if os.path.exists(target):
        suffix = datetime.now(gettz("Europe/Amsterdam")).strftime("%Y%m%d_%H%M%S")
        target = os.path.join(category_root, f"{base_name}_{suffix}")

    try:
        shutil.move(current_outdir, target)
        return target
    except Exception as e:
        log(f"[MOVE FAIL] {current_outdir} → {target}: {e}")
        return current_outdir


def _replace_path_prefix(value, old_prefix: str, new_prefix: str):
    """Update paden in nested dict/list-structuren nadat een publicatiemap is verplaatst."""
    if isinstance(value, dict):
        for k, v in list(value.items()):
            if isinstance(v, str) and old_prefix and v.startswith(old_prefix):
                value[k] = new_prefix + v[len(old_prefix):]
            else:
                _replace_path_prefix(v, old_prefix, new_prefix)
    elif isinstance(value, list):
        for item in value:
            _replace_path_prefix(item, old_prefix, new_prefix)
    return value

# ==== Core ====
def scan_recent(days_back=DAYS_BACK_DEFAULT, max_pages=10, download_dir="recent_downloads",
                throttle_s=0.25, zip_max_mb=200, zip_follow_nested=False,
                analyze_openai=False, openai_model=OPENAI_MODEL_DEFAULT):
    """Scan TenderNed publicaties in de laatste N dagen.

    Robuustheid:
    - Netwerk calls zijn timeboxed (max ~60s per call); errors worden gelogd en de scan gaat door.
    - PDF parsing is timeboxed (max 60s per PDF) via een persistent worker-process.
    - Extra timing logs om te zien waar het 'hangt'.
    """

    os.makedirs(download_dir, exist_ok=True)

    # Toon actieve TenderNed API-filters aan het begin van de run.
    log(f"Actieve TenderNed filters: {build_tenderned_list_params(page=0, size=50)}")

    # 1 persistente parser-worker voor alle PDFs in deze run (serieel, maar killable bij hang).
    pdf_parser = PdfParseSupervisor(timeout_s=PDF_PARSE_TIMEOUT_S)

    matched_publications = {}
    # Per publicatie bewaren we welke documenten vermoedelijk de leidraad zijn.
    leidraad_candidates_by_publication = {}
    supporting_doc_candidates_by_publication = {}
    openai_results_by_publication = {}
    processed = 0
    skipped_cpv = 0
    seen = 0
    cpv_present = 0
    cpv_missing = 0

    try:
        for page in range(max_pages):
            t_page = time.monotonic()
            data = fetch_list_page(page=page, size=50)
            items = data.get("content") or data.get("items") or []
            if not items:
                break

            dur_page = time.monotonic() - t_page
            if dur_page >= SLOW_STEP_S and VERBOSE_STEPS:
                log(f"[SLOW LIST] pagina {page} {_fmt_dur(dur_page)}")

            any_recent = False

            for it in items:
                pid = it.get("publicatieId") or it.get("id")
                pdt = it.get("publicatieDatum") or it.get("datum") or it.get("publicationDate")
                if not within_last_days(pdt, days_back=days_back):
                    continue

                any_recent = True
                seen += 1

                # detail ophalen voor rijkere velden + CPV
                t_detail = time.monotonic()
                detail = fetch_detail(pid)
                dur_detail = time.monotonic() - t_detail
                if dur_detail >= SLOW_STEP_S and VERBOSE_STEPS:
                    log(f"[SLOW DETAIL] {pid} {_fmt_dur(dur_detail)}")

                # CPV verzamelen uit *zowel* list als detail
                cpv_all_display, cpv_all_match = collect_all_cpv(it, detail)
                if cpv_all_display:
                    cpv_present += 1
                else:
                    cpv_missing += 1

                # nette kopregel
                naam = detail.get("aanbestedingNaam") or it.get("aanbestedingNaam") or ""
                org = detail.get("opdrachtgeverNaam") or it.get("opdrachtgeverNaam") or ""
                print(f"[{pid}] {pdt} — {naam} — {org}")
                print(
                    f"   CPV (samengevoegd list+detail): {', '.join(cpv_all_display) if cpv_all_display else '(geen CPV in API)'}"
                )

                # CPV-whitelist check (alleen doorgaan als er overlap is)
                if not (cpv_all_match & CPV_WHITELIST):
                    print("   → CPV niet in whitelist → documenten overslaan")
                    skipped_cpv += 1
                    hr()
                    continue

                # Documenten ophalen
                t_docs = time.monotonic()
                docs = fetch_documents(pid)
                dur_docs = time.monotonic() - t_docs
                if dur_docs >= SLOW_STEP_S and VERBOSE_STEPS:
                    log(f"[SLOW DOCS] {pid} {_fmt_dur(dur_docs)}")

                print(
                    f"   → CPV match gevonden → documenten lezen (PDF + PDF’s in ZIP). Aantal documenten: {len(docs)}"
                )
                outdir = os.path.join(download_dir, str(pid))
                os.makedirs(outdir, exist_ok=True)

                any_keyword = False
                # Wordt gebruikt om na OpenAI-analyse de publicatiemap te sorteren naar GO of Overig.
                output_category = "Overig"
                # Bewaar alleen documenten die daadwerkelijk zijn gedownload/verwerkt.
                # Leidraad-detectie gebeurt bewust pas NA de keyword-filter.
                downloaded_documents = []

                for i, d in enumerate(docs, start=1):
                    dname = d.get("documentNaam") or f"doc_{i}"
                    dtype = ((d.get("typeDocument") or {}).get("code")) or ""
                    dlrel = (((d.get("links") or {}).get("download") or {}).get("href")) or ""


                    if not dlrel:
                        print(f"     [{i}] {dname} ({dtype or 'onbekend'}) → geen download-link")
                        continue

                    url = dlrel if dlrel.startswith("http") else WEB_BASE + dlrel

                    # --- PDF direct ---
                    if (dtype and dtype.lower() == "pdf") or dname.lower().endswith(".pdf"):
                        fn = dname if dname.lower().endswith(".pdf") else (dname + ".pdf")
                        fpath = os.path.join(outdir, fn)
                        try:
                            t_dl = time.monotonic()
                            blob = download_bytes(url)
                            dur_dl = time.monotonic() - t_dl
                            if dur_dl >= SLOW_STEP_S and VERBOSE_STEPS:
                                log(f"[SLOW DL] {pid} {_fmt_dur(dur_dl)} {dname}")

                            status, hits = process_pdf_blob(blob, fpath, pdf_parser, label=f"{pid}/{fn}")
                            downloaded_documents.append({
                                "title": dname,
                                "filename": fn,
                                "path": fpath,
                                "source": "direct_pdf",
                                "read_status": status,
                                "keyword_hits": hits,
                            })

                            if status == "OK":
                                if hits:
                                    any_keyword = True
                                    print(
                                        f"     [{i}] {fn} → download: OK | lezen: OK | KEYWORDS: {', '.join(hits)}"
                                    )
                                else:
                                    print(f"     [{i}] {fn} → download: OK | lezen: OK | keywords: -")
                            elif status == "TIMEOUT":
                                print(
                                    f"     [{i}] {fn} → download: OK | lezen: TIMEOUT (> {PDF_PARSE_TIMEOUT_S}s) | keywords: -"
                                )
                            else:
                                print(f"     [{i}] {fn} → download: OK | lezen: FAIL")

                        except Exception as e:
                            print(f"     [{i}] {dname} (pdf) → download/lezen FAIL: {e}")

                        time.sleep(throttle_s)
                        continue

                    # --- ZIP (met PDF's) ---
                    if looks_like_zip(dtype, dname):
                        try:
                            t_dl = time.monotonic()
                            blob = download_bytes(url)
                            dur_dl = time.monotonic() - t_dl
                            if dur_dl >= SLOW_STEP_S and VERBOSE_STEPS:
                                log(f"[SLOW DL] {pid} {_fmt_dur(dur_dl)} {dname}")

                            # size check
                            size_mb = len(blob) / (1024 * 1024)
                            if size_mb > float(zip_max_mb):
                                print(
                                    f"     [{i}] {dname} (zip ~{size_mb:.1f} MB) → overgeslagen (groter dan {zip_max_mb} MB)"
                                )
                                continue

                            # submap voor zip-inhoud
                            zip_stem = os.path.splitext(dname)[0]
                            zip_outdir = os.path.join(outdir, zip_stem)
                            os.makedirs(zip_outdir, exist_ok=True)

                            found_any_pdf = False
                            found_keywords_overall = []

                            for (label, fname, data, is_pdf, is_zip) in safe_zip_iter(
                                blob,
                                follow_nested=zip_follow_nested,
                                base_outdir=zip_outdir,
                                parent_label=zip_stem,
                                throttle_s=throttle_s,
                            ):
                                if is_pdf:
                                    found_any_pdf = True
                                    save_as = os.path.join(
                                        zip_outdir,
                                        fname if fname.lower().endswith(".pdf") else (fname + ".pdf"),
                                    )

                                    status, hits = process_pdf_blob(
                                        data,
                                        save_as,
                                        pdf_parser,
                                        label=f"{pid}/{zip_stem}/{fname}",
                                    )
                                    downloaded_documents.append({
                                        "title": fname,
                                        "filename": fname,
                                        "path": save_as,
                                        "source": f"zip:{dname}",
                                        "read_status": status,
                                        "keyword_hits": hits,
                                    })

                                    if status == "OK":
                                        if hits:
                                            any_keyword = True
                                            found_keywords_overall.extend(hits)
                                            print(
                                                f"       [ZIP] {label} → download: OK | lezen: OK | KEYWORDS: {', '.join(hits)}"
                                            )
                                        else:
                                            print(f"       [ZIP] {label} → download: OK | lezen: OK | keywords: -")
                                    elif status == "TIMEOUT":
                                        print(
                                            f"       [ZIP] {label} → download: OK | lezen: TIMEOUT (> {PDF_PARSE_TIMEOUT_S}s)"
                                        )
                                    else:
                                        print(f"       [ZIP] {label} → download: OK | lezen: FAIL")
                                else:
                                    # we loggen non-PDF entries kort
                                    if is_zip:
                                        note = "(nested zip; genegeerd)" if not zip_follow_nested else "(nested zip; gevolgd)"
                                    else:
                                        note = "(geen pdf)"
                                    print(f"       [ZIP] {label} → {note}")

                            if not found_any_pdf:
                                print(f"     [{i}] {dname} (zip) → geen PDF’s binnen zip")
                            else:
                                if found_keywords_overall:
                                    # toon unieke keywords
                                    uniq = sorted(set(found_keywords_overall), key=lambda x: found_keywords_overall.index(x))
                                    print(
                                        f"     [{i}] {dname} (zip) → samenvatting: KEYWORDS in zip: {', '.join(uniq)}"
                                    )
                                else:
                                    print(f"     [{i}] {dname} (zip) → samenvatting: geen keyword hits in PDFs")

                        except zipfile.BadZipFile:
                            print(
                                f"     [{i}] {dname} (zip) → beschadigd of ongeldig ZIP-archief (BadZipFile)"
                            )
                        except Exception as e:
                            print(f"     [{i}] {dname} (zip) → verwerken FAIL: {e}")

                        time.sleep(throttle_s)
                        continue

                    # --- overige bestandssoorten ---
                    print(f"     [{i}] {dname} ({dtype or 'onbekend'}) → overgeslagen (geen pdf/zip)")

                if any_keyword:
                    matched_publications[pid] = naam

                    # Pas NU, na CPV én keyword-hit, zoeken we de leidraad.
                    # Zo stuur je later alleen dure OpenAI-analyse op aanbestedingen die al door beide filters zijn.
                    leidraad_candidates, supporting_doc_candidates = find_leidraad_candidates(downloaded_documents)

                    if leidraad_candidates:
                        leidraad_candidates_by_publication[pid] = leidraad_candidates
                        best = leidraad_candidates[0]
                        print(f"   → LEIDRAAD-KANDIDAAT NA KEYWORD-FILTER: {best['name']} | score: {best['score']} | match: {', '.join(best['title_hits'])} | pad: {best['path']}")

                        if analyze_openai:
                            print(f"   → OpenAI-analyse gestart voor leidraad: {best['name']}")
                            analysis_result = analyze_leidraad_with_openai(
                                pdf_path=best["path"],
                                publication_id=str(pid),
                                title=naam,
                                organisation=org,
                                publication_date=str(pdt or ""),
                                cpv_codes=cpv_all_display,
                                model=openai_model,
                                output_dir=outdir,
                            )
                            openai_results_by_publication[pid] = analysis_result
                            if analysis_result.get("status") == "OK":
                                a = analysis_result.get("analysis") or {}
                                decision = str(a.get("decision") or "").strip().upper()
                                if decision == "GO":
                                    output_category = "GO"
                                print(f"   → OpenAI oordeel: {a.get('decision')} | confidence: {a.get('confidence')} | {a.get('reason_short')}")
                                if analysis_result.get("output_path"):
                                    print(f"   → OpenAI analyse opgeslagen: {analysis_result['output_path']}")
                            else:
                                print(f"   → OpenAI analyse niet gelukt ({analysis_result.get('status')}): {analysis_result.get('error', 'geen geldige JSON teruggekregen')}")
                        else:
                            print("   → OpenAI-analyse staat uit. Gebruik --analyze_openai om deze leidraad te uploaden/analyseren.")

                        if len(leidraad_candidates) > 1:
                            print("   → Overige leidraad-kandidaten:")
                            for cand in leidraad_candidates[1:]:
                                print(f"      - {cand['name']} | score: {cand['score']} | match: {', '.join(cand['title_hits'])} | pad: {cand['path']}")
                    else:
                        print("   → Keyword-hit gevonden, maar geen leidraad-kandidaat op documenttitel")

                    if supporting_doc_candidates:
                        supporting_doc_candidates_by_publication[pid] = supporting_doc_candidates
                        print("   → Aanvullende tenderdocument-kandidaten na keyword-filter:")
                        for cand in supporting_doc_candidates[:5]:
                            print(f"      - {cand['name']} | match: {', '.join(cand['title_hits'])} | pad: {cand['path']}")
                else:
                    print("   → Geen keyword-hit → leidraad-check overgeslagen")

                # Sorteer pas ná de eventuele OpenAI-analyse, want dan weten we pas of iets echt GO is.
                # Zonder --analyze_openai bewaren we de oude structuur, omdat er dan geen GO-oordeel bestaat.
                if analyze_openai:
                    old_outdir = outdir
                    outdir = _safe_move_publication_folder(outdir, download_dir, pid, output_category)
                    if outdir != old_outdir:
                        _replace_path_prefix(downloaded_documents, old_outdir, outdir)
                        _replace_path_prefix(leidraad_candidates_by_publication.get(pid), old_outdir, outdir)
                        _replace_path_prefix(supporting_doc_candidates_by_publication.get(pid), old_outdir, outdir)
                        _replace_path_prefix(openai_results_by_publication.get(pid), old_outdir, outdir)
                    print(f"   → Documentmap opgeslagen onder: {output_category}/{os.path.basename(outdir)}")

                processed += 1
                hr()

            if not any_recent:
                break

    finally:
        # Zorg dat het worker-process altijd netjes wordt afgesloten.
        pdf_parser.shutdown()

    # Samenvatting
    print("\nSAMENVATTING")
    print(f"- Publicaties gezien (laatste {days_back} dagen): {seen}")
    print(f"- Met CPV-gegevens aanwezig:                   {cpv_present}")
    print(f"- Zonder CPV-gegevens (API gaf niets):         {cpv_missing}")
    print(f"- Documenten verwerkt (na CPV-filter):         {processed}")
    print(f"- Overgeslagen door CPV-filter:                {skipped_cpv}")
    print(f"- Met keyword-hit én leidraad-kandidaat:        {len(leidraad_candidates_by_publication)}")
    if analyze_openai:
        print(f"- OpenAI-analyses uitgevoerd/geprobeerd:        {len(openai_results_by_publication)}")
        if openai_results_by_publication:
            print("- OpenAI-oordelen:")
            for pid, result in openai_results_by_publication.items():
                if result.get("status") == "OK":
                    a = result.get("analysis") or {}
                    print(f"   - ID {pid}: {a.get('decision')} | confidence: {a.get('confidence')} | {a.get('reason_short')}")
                    if result.get("output_path"):
                        print(f"     JSON: {result['output_path']}")
                else:
                    print(f"   - ID {pid}: {result.get('status')} | {result.get('error', 'geen geldige JSON teruggekregen')}")
    if leidraad_candidates_by_publication:
        print("- Leidraad-kandidaten:")
        for pid, candidates in leidraad_candidates_by_publication.items():
            best = candidates[0]
            print(f"   - ID {pid}: {best['name']} (score: {best['score']}, pad: {best['path']})")
    if matched_publications:
        print(f"- ✅ Keyword hits (keywords: {', '.join(KEYWORDS)}):")
        for pid, title in matched_publications.items():
            print(f"   - {title} (ID: {pid})")
    else:
        print(f"- ❌ Geen keyword hits gevonden (keywords: {', '.join(KEYWORDS)})")

    # Laatste terminalblok: expliciet overzicht van alle GO's uit de OpenAI API-call.
    # Dit staat bewust helemaal onderaan, zodat je na een run direct ziet of er actie nodig is.
    print("\nGO-OVERZICHT OPENAI")
    if not analyze_openai:
        print("- OpenAI-analyse stond uit; er zijn dus geen GO/NO_GO/MAYBE-oordelen opgehaald.")
    else:
        go_results = []
        for pid, result in openai_results_by_publication.items():
            if result.get("status") != "OK":
                continue

            analysis = result.get("analysis") or {}
            decision = str(analysis.get("decision") or "").strip().upper()
            if decision == "GO":
                go_results.append((pid, result, analysis))

        if go_results:
            print(f"- ✅ GO gegeven door OpenAI: {len(go_results)}")
            for pid, result, analysis in go_results:
                title = result.get("publication_title") or matched_publications.get(pid) or "onbekende titel"
                confidence = analysis.get("confidence")
                reason = analysis.get("reason_short") or "geen korte reden opgegeven"
                leidraad_path = result.get("leidraad_path") or "onbekend"

                print(f"   - ID {pid}: {title}")
                print(f"     Confidence: {confidence}")
                print(f"     Reden: {reason}")
                print(f"     Leidraad: {leidraad_path}")
                if result.get("output_path"):
                    print(f"     JSON: {result['output_path']}")
        else:
            print("- ❌ Geen GO's gegeven door OpenAI.")


def main():
    ap = argparse.ArgumentParser(
        description="Scan laatste N dagen; CPV uit list+detail; lees PDF's én PDF’s in ZIP; zoek keywords; optioneel OpenAI-analyse op leidraad."
    )
    ap.add_argument("--days", type=int, default=DAYS_BACK_DEFAULT, help="Aantal dagen terug (default 2).")
    ap.add_argument("--pages", type=int, default=10, help="Max # lijstpagina’s (x50).")
    ap.add_argument("--download_dir", default="recent_downloads", help="Map voor downloads.")
    ap.add_argument("--throttle", type=float, default=0.25, help="Pauze (s) tussen downloads (vriendelijk blijven).")
    ap.add_argument("--zip_max_mb", type=float, default=200.0, help="Max ZIP-grootte om te verwerken (MB).")
    ap.add_argument("--zip_follow_nested", action="store_true", help="Volg nested ZIPs (zip-in-zip). Default: uit.")
    ap.add_argument("--analyze_openai", action="store_true", help="Upload/analyseer de beste leidraad-kandidaat via OpenAI. Vereist OPENAI_API_KEY.")
    ap.add_argument("--openai_model", default=OPENAI_MODEL_DEFAULT, help=f"OpenAI model voor analyse (default: {OPENAI_MODEL_DEFAULT}).")
    args = ap.parse_args()

    return scan_recent(
        days_back=args.days,
        max_pages=args.pages,
        download_dir=args.download_dir,
        throttle_s=args.throttle,
        zip_max_mb=args.zip_max_mb,
        zip_follow_nested=args.zip_follow_nested,
        analyze_openai=args.analyze_openai,
        openai_model=args.openai_model,
    )

if __name__ == "__main__":
    sys.exit(main() or 0)
