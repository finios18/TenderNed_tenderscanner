#!/usr/bin/env python3
"""
Lokale test-runner voor aanbestedingsleidraden.

Doel:
- Test exact dezelfde OpenAI-analyseprompt als in het bestaande TenderNed-script.
- Gebruik lokale PDF-bestanden als input.
- Sla per leidraad de volledige JSON-output op.
- Toon onderaan een compact GO/MAYBE/NO_GO overzicht.

Gebruik:
    cd naar plek en dan:
    $env:OPENAI_API_KEY="jouw_openai_api_key"
    python test_local_leidraden_openai.py ./aanbestedingen_glenn

Optioneel:
    python test_local_leidraden_openai.py ./leidraden --output_dir test_results
    python test_local_leidraden_openai.py ./leidraden --openai_model gpt-5.4-mini
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


OPENAI_MODEL_DEFAULT = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_ANALYSIS_TIMEOUT_S = 180


def build_tender_analysis_prompt(
    publication_id: str,
    title: str,
    organisation: str,
    publication_date: str,
    cpv_codes,
) -> str:
    """Exact dezelfde promptstructuur als in het bestaande TenderNed-script."""
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
3. De opdracht valt binnen onze primaire domeinen, OF is een brede flexibele personeelsinhuur-opdracht waarin professionals via detachering/ZZP-bemiddeling worden geleverd.
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


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON parser: accepteert zuivere JSON of tekst met een JSON-object erin."""
    if not text:
        return None

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    return None


def discover_pdf_files(inputs: List[str]) -> List[Path]:
    """Accepteert losse PDF's en/of mappen met PDF's."""
    pdfs: List[Path] = []

    for raw in inputs:
        path = Path(raw).expanduser().resolve()

        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
            continue

        if path.is_dir():
            pdfs.extend(sorted(path.glob("*.pdf")))
            continue

        print(f"[WAARSCHUWING] Geen PDF of map gevonden: {raw}", file=sys.stderr)

    # Dedupe, behoud volgorde
    seen = set()
    unique_pdfs = []
    for pdf in pdfs:
        if pdf not in seen:
            unique_pdfs.append(pdf)
            seen.add(pdf)

    return unique_pdfs


def make_test_metadata(pdf_path: Path, index: int) -> Dict[str, Any]:
    """
    Bewust minimale metadata.

    Reden:
    - In deze test willen we weten of de leidraad zelf voldoende informatie bevat.
    - De bestaande prompt blijft exact hetzelfde.
    - Velden die normaal uit TenderNed komen, vullen we neutraal in.
    """
    return {
        "publication_id": f"LOCAL-TEST-{index:03d}",
        "title": pdf_path.stem,
        "organisation": "onbekend",
        "publication_date": "onbekend",
        "cpv_codes": [],
    }


def analyze_leidraad_with_openai(
    pdf_path: Path,
    publication_id: str,
    title: str,
    organisation: str,
    publication_date: str,
    cpv_codes,
    model: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """
    Upload één lokale leidraad-PDF naar OpenAI en vraag dezelfde JSON-analyse terug
    als in het bestaande TenderNed-script.
    """
    if not pdf_path.exists():
        return {
            "status": "SKIPPED",
            "error": f"PDF bestaat niet: {pdf_path}",
            "leidraad_path": str(pdf_path),
        }

    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "status": "SKIPPED",
            "error": "OPENAI_API_KEY ontbreekt; OpenAI-analyse overgeslagen",
            "leidraad_path": str(pdf_path),
        }

    try:
        from openai import OpenAI
    except Exception as e:
        return {
            "status": "SKIPPED",
            "error": f"openai package niet geïnstalleerd of niet importeerbaar: {e}",
            "leidraad_path": str(pdf_path),
        }

    client = OpenAI(timeout=OPENAI_ANALYSIS_TIMEOUT_S)
    prompt = build_tender_analysis_prompt(
        publication_id=publication_id,
        title=title,
        organisation=organisation,
        publication_date=publication_date,
        cpv_codes=cpv_codes,
    )

    try:
        with pdf_path.open("rb") as f:
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
        parsed = extract_json_object(raw_text)

        result = {
            "status": "OK" if parsed is not None else "PARSE_FAIL",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "publication_id": publication_id,
            "publication_title": title,
            "organisation": organisation,
            "publication_date": publication_date,
            "cpv_codes": cpv_codes,
            "leidraad_path": str(pdf_path),
            "model": model,
            "file_id": uploaded.id,
            "analysis": parsed,
            "raw_output": raw_text,
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in pdf_path.stem)
        out_path = output_dir / f"openai_analysis_{publication_id}_{safe_name}.json"

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        result["output_path"] = str(out_path)
        return result

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "publication_id": publication_id,
            "publication_title": title,
            "leidraad_path": str(pdf_path),
            "model": model,
        }


def print_single_result(result: Dict[str, Any]) -> None:
    status = result.get("status")
    title = result.get("publication_title") or Path(result.get("leidraad_path", "")).name

    print("-" * 100)
    print(f"BESTAND: {title}")
    print(f"STATUS:  {status}")

    if status == "OK":
        analysis = result.get("analysis") or {}
        print(f"OORDEEL: {analysis.get('decision')}")
        print(f"CONF.:   {analysis.get('confidence')}")
        print(f"REDEN:   {analysis.get('reason_short')}")
        print(f"JSON:    {result.get('output_path')}")
    else:
        print(f"ERROR:   {result.get('error', 'Geen geldige JSON teruggekregen')}")
        if result.get("raw_output"):
            print("RAW OUTPUT:")
            print(result["raw_output"][:1500])


def print_go_overview(results: List[Dict[str, Any]]) -> None:
    print("\nGO-OVERZICHT OPENAI")
    print("-" * 100)

    if not results:
        print("Geen resultaten.")
        return

    go_count = 0
    maybe_count = 0
    no_go_count = 0
    other_count = 0

    for result in results:
        analysis = result.get("analysis") or {}
        decision = str(analysis.get("decision") or "").strip().upper()

        if decision == "GO":
            go_count += 1
        elif decision == "MAYBE":
            maybe_count += 1
        elif decision == "NO_GO":
            no_go_count += 1
        else:
            other_count += 1

        title = result.get("publication_title") or Path(result.get("leidraad_path", "")).name
        confidence = analysis.get("confidence")
        reason = analysis.get("reason_short") or result.get("error") or "geen reden"

        print(f"- {decision or result.get('status')}: {title}")
        print(f"  Confidence: {confidence}")
        print(f"  Reden: {reason}")
        if result.get("output_path"):
            print(f"  JSON: {result['output_path']}")

    print("-" * 100)
    print(f"Totaal GO:     {go_count}")
    print(f"Totaal MAYBE:  {maybe_count}")
    print(f"Totaal NO_GO:  {no_go_count}")
    print(f"Overig/fout:   {other_count}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test lokale aanbestedingsleidraden met dezelfde OpenAI-prompt als het TenderNed-script."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Een of meer PDF-bestanden of mappen met PDF-bestanden.",
    )
    parser.add_argument(
        "--output_dir",
        default="local_openai_test_results",
        help="Map waarin JSON-resultaten worden opgeslagen.",
    )
    parser.add_argument(
        "--openai_model",
        default=OPENAI_MODEL_DEFAULT,
        help=f"OpenAI model voor analyse. Default: {OPENAI_MODEL_DEFAULT}",
    )
    args = parser.parse_args()

    pdfs = discover_pdf_files(args.inputs)
    if not pdfs:
        print("Geen PDF-bestanden gevonden.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()

    print(f"Aantal PDF's gevonden: {len(pdfs)}")
    print(f"Model: {args.openai_model}")
    print(f"Output map: {output_dir}")

    results: List[Dict[str, Any]] = []

    for index, pdf_path in enumerate(pdfs, start=1):
        metadata = make_test_metadata(pdf_path, index)

        print(f"\nAnalyse gestart: {pdf_path.name}")

        result = analyze_leidraad_with_openai(
            pdf_path=pdf_path,
            publication_id=metadata["publication_id"],
            title=metadata["title"],
            organisation=metadata["organisation"],
            publication_date=metadata["publication_date"],
            cpv_codes=metadata["cpv_codes"],
            model=args.openai_model,
            output_dir=output_dir,
        )

        results.append(result)
        print_single_result(result)

    summary_path = output_dir / "summary_all_results.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print_go_overview(results)
    print(f"\nSamenvatting opgeslagen: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
