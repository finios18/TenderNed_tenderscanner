"""Opt-in persistent scan route; legacy tender_scan.py remains independently usable."""
import argparse
from datetime import date, datetime, timedelta
from email.message import EmailMessage
import hashlib
import json
import os
from pathlib import Path
import smtplib
from ssl import create_default_context
from zoneinfo import ZoneInfo

from go_mail_report import create_mail_report
from scanner_config import apply_config, load_config
from scanner_database import DatabaseError, Store, connect_database


class IncompleteRetrieval(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def selection_digest(config, scanner):
    return digest({"api": config["api"], "filters": config["filters"], "prompt": config["_prompt_text"],
                   "model": config["scan"].get("openai_model", scanner.OPENAI_MODEL_DEFAULT),
                   "ai": config["scan"]["analyze_openai"],
                   "zip_max_mb": config["scan"]["zip_max_mb"], "nested": config["scan"]["zip_follow_nested"],
                   "lead_document_keywords": scanner.AANBESTEDING_KEYWORDS, "processor_version": 1})


def retrieval_window(first_date, retrieved_through, overlap_days, today):
    end = today - timedelta(days=1)
    start = first_date if retrieved_through is None else max(first_date, retrieved_through + timedelta(days=1-overlap_days))
    return start, end


def is_due(config, state, today):
    schedule = config["schedule"]
    start = date.fromisoformat(schedule["start_date"])
    last = state["last_completed_day"]
    if not schedule["enabled"] or today < start:
        return False
    interval = schedule["interval_days"]
    current_slot = start + timedelta(days=((today - start).days // interval) * interval)
    # Retry missed slots without shifting the next regular scan day.
    return last is None or last < current_slot


def strict_json(scanner, url, params=None):
    data = scanner.get_json(url, params=params)
    if data is None:
        raise IncompleteRetrieval("TenderNed-aanroep mislukt; ophaalvoortgang wordt niet verplaatst")
    return data


def publication_day(scanner, item):
    value = item.get("publicatieDatum") or item.get("datum") or item.get("publicationDate")
    try:
        parsed = scanner.parse_dt(value)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None:
        raise IncompleteRetrieval("Publicatie zonder geldige publicatiedatum")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo("Europe/Amsterdam"))
    return parsed.date()


def retrieve_items(scanner, start, end, max_pages):
    """Require stable totalElements and unique IDs; never treat API errors as empty pages."""
    seen, expected = set(), None
    for page in range(max_pages):
        params = scanner.build_tenderned_list_params(page=page, size=50)
        params.update(publicatieDatumPreset="AGP", publicatieDatumVanaf=start.isoformat(),
                      publicatieDatumTot=end.isoformat(), sort="tappublicatiedatum")
        data = strict_json(scanner, scanner.TNS_BASE, params)
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise IncompleteRetrieval("Onverwachte lijstresponse van TenderNed")
        total = data.get("totalElements")
        if type(total) is not int or total < 0:
            raise IncompleteRetrieval("totalElements ontbreekt of is ongeldig; volledigheid kan niet worden vastgesteld")
        if expected is not None and total != expected:
            raise IncompleteRetrieval("Resultaataantal veranderde tijdens paginering; probeer opnieuw")
        expected = total
        items = data["content"]
        if len(items) > 50:
            raise IncompleteRetrieval("Onverwachte paginagrootte")
        for item in items:
            if not isinstance(item, dict):
                raise IncompleteRetrieval("Ongeldige publicatie in lijst")
            pid = str(item.get("publicatieId") or item.get("id") or "")
            if not pid.isdigit() or pid in seen:
                raise IncompleteRetrieval("Ontbrekende of dubbele publicatie-ID tijdens paginering")
            if not start <= publication_day(scanner, item) <= end:
                raise IncompleteRetrieval("TenderNed gaf een publicatie buiten het gevraagde datumvenster")
            seen.add(pid)
            if len(seen) > expected:
                raise IncompleteRetrieval("Meer publicaties dan totalElements")
            yield pid, item
        if len(seen) == expected:
            return
        if not items or data.get("last") is True:
            raise IncompleteRetrieval("Pagina's eindigen vóór het verwachte resultaataantal")
    raise IncompleteRetrieval("Paginalimiet bereikt vóór alle publicaties zijn opgehaald")


def metadata(scanner, publication_id, item):
    detail = strict_json(scanner, f"{scanner.TNS_BASE}/{publication_id}")
    if not isinstance(detail, dict) or not detail:
        raise IncompleteRetrieval("Onverwachte detailresponse")
    # Rejected CPV publications do not need document lists.
    _, cpv = scanner.collect_all_cpv(item, detail)
    documents = []
    if cpv & scanner.CPV_WHITELIST:
        data = strict_json(scanner, f"{scanner.TNS_BASE}/{publication_id}/documenten")
        documents = data if isinstance(data, list) else data.get("documenten") if isinstance(data, dict) else None
        if not isinstance(documents, list) or any(not isinstance(doc, dict) for doc in documents):
            raise IncompleteRetrieval("Onverwachte documentenresponse")
    return {"item": item, "detail": detail, "documents": documents}


def outcome(report):
    reasons = {event["reason"] for event in report["events"]}
    terminal = {"cpv_no_match", "no_content_keyword_match", "unsupported_document_type",
                "nested_zip_disabled", "openai_no_go", "openai_maybe", "openai_disabled"}
    # Technical failures and incomplete documents win over a negative keyword/CPV result.
    incomplete = reasons - terminal
    if incomplete:
        return None, ", ".join(sorted(incomplete))
    results = report["results"]
    if results:
        result = results[0]
        analysis = result.get("analysis")
        decision = str(analysis.get("decision", "")).strip().upper() if isinstance(analysis, dict) else ""
        if result.get("status") != "OK" or decision not in {"GO", "MAYBE", "NO_GO"}:
            return None, "Ongeldig AI-oordeel"
        result["analysis"]["decision"] = decision
        return result, None
    if not reasons:
        return None, "Publicatie zonder vastgestelde verwerkingsuitkomst"
    return None, None


def process_one(scanner, config, row, output_dir):
    payload = row["payload"]
    settings = config["scan"]
    return scanner.scan_recent(
        publication_items=[payload["item"]],
        detail_loader=lambda _: payload["detail"], documents_loader=lambda _: payload["documents"],
        download_dir=str(output_dir), throttle_s=settings["throttle"],
        zip_max_mb=settings["zip_max_mb"], zip_follow_nested=settings["zip_follow_nested"],
        analyze_openai=settings["analyze_openai"],
        openai_model=settings.get("openai_model", scanner.OPENAI_MODEL_DEFAULT))


def smtp_settings():
    names = ("SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_TO")
    if any(not os.environ.get(name) for name in names):
        raise ValueError("SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD en MAIL_TO zijn vereist voor e-mail")
    port = int(os.environ["SMTP_PORT"])
    if not 1 <= port <= 65535:
        raise ValueError("Ongeldige SMTP_PORT")
    return port


def deliver_mail(store, batch, output_dir, github_url):
    port = smtp_settings()
    report = create_mail_report(batch["results"], output_dir, github_url)
    message = EmailMessage()
    message["Subject"] = report["subject"]
    message["From"] = os.environ["SMTP_USERNAME"]
    message["To"] = batch["recipient"]
    message["Message-ID"] = f"<tenderscanner-{batch['batch_id']}@tenderscanner.local>"
    message.set_content((Path(output_dir) / "mail_summary.txt").read_text(encoding="utf-8"))
    attachment = Path(output_dir) / "GO-aanbestedingen.html"
    if attachment.exists():
        message.add_attachment(attachment.read_bytes(), maintype="text", subtype="html", filename=attachment.name)
    context = create_default_context()
    factory = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    # Login/connection failure occurs before the sending marker, and is safe to retry.
    kwargs = {"context": context} if port == 465 else {}
    with factory(os.environ["SMTP_SERVER"], port, timeout=60, **kwargs) as smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        store.mail_status(batch["batch_id"], "sending")
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError("Niet alle ontvangers hebben het bericht geaccepteerd; controleer mailbatch")
        store.mail_status(batch["batch_id"], "sent")


def run_scan(scanner, store, config, output_dir, today, scheduled=False, send_email=False, github_url=""):
    if "retrieval" not in config or "schedule" not in config:
        raise ValueError("Database-scans vereisen retrieval en schedule in het profiel")
    if config["scan"]["analyze_openai"] and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY ontbreekt")
    if send_email:
        smtp_settings()
    apply_config(scanner, config)
    company_id, selection_hash = config["id"], selection_digest(config, scanner)
    with store.company_lock(company_id):
        first_date = date.fromisoformat(config["retrieval"]["first_publication_date"])
        state = store.company(company_id, first_date, selection_hash)
        if scheduled and not is_due(config, state, today):
            print("Bedrijf is vandaag niet aan de beurt")
            return False
        start, end = retrieval_window(first_date, state["retrieved_through"], config["retrieval"]["overlap_days"], today)
        if first_date > end:
            print("Nog geen volledige kalenderdag beschikbaar vanaf first_publication_date")
            return False
        run_id = store.start_run(company_id, start, end, github_url)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results, issues = [], []
        retrieval_complete = False
        try:
            if start <= end:
                for pid, item in retrieve_items(scanner, start, end, config["scan"]["pages"]):
                    payload = metadata(scanner, pid, item)
                    fingerprint = digest({"selection": selection_hash, "publication": payload})
                    store.save_publication(company_id, pid, fingerprint, selection_hash, payload)
                store.advance_retrieval(company_id, end)
            retrieval_complete = True
            for row in store.pending(company_id, selection_hash):
                try:
                    # Refresh incomplete metadata/doc lists before a retry, including old publications.
                    if row["attempts"]:
                        payload = metadata(scanner, row["publication_id"], row["payload"]["item"])
                        fingerprint = digest({"selection": selection_hash, "publication": payload})
                        store.save_publication(company_id, row["publication_id"], fingerprint, selection_hash, payload)
                        row.update(payload=payload, fingerprint=fingerprint)
                    report = process_one(scanner, config, row, output_dir / "publications" / row["publication_id"])
                    result, retry_reason = outcome(report)
                except Exception as exc:
                    result, retry_reason = None, f"Verwerking mislukt ({type(exc).__name__})"
                store.save_processing(row, result, retry_reason)
                if result:
                    results.append(result)
                if retry_reason:
                    issues.append({"publication_id": row["publication_id"], "reason": retry_reason})
            (output_dir / "current_scan_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            remaining = store.unfinished_count(company_id, selection_hash)
            if send_email:
                # Prepared batches from earlier attempts are sent before new batches.
                # At most one batch per execution; remaining queued GO's are picked up next run.
                batch = store.prepare_mail(company_id, selection_hash, os.environ["MAIL_TO"])
                deliver_mail(store, batch, output_dir, github_url)
                if store.outstanding_mail_count(company_id, selection_hash):
                    raise RuntimeError("Er staan nog GO-resultaten klaar voor een volgende mailbatch")
            else:
                create_mail_report(results, output_dir, github_url)
            if remaining:
                raise RuntimeError(f"{remaining} publicaties wachten op herverwerking; zie database en artifact")
            store.complete_day(company_id, today)
            store.finish_run(run_id, "complete")
            return True
        except Exception as exc:
            # Store a controlled error; do not persist potentially secret-bearing exception text.
            error = str(exc) if isinstance(exc, (IncompleteRetrieval, DatabaseError)) else f"Uitvoering onvolledig ({type(exc).__name__})"
            store.finish_run(run_id, "incomplete" if retrieval_complete else "failed", error)
            raise
        finally:
            (output_dir / "database_run.json").write_text(json.dumps({
                "run_id": run_id, "company_id": company_id, "window_from": str(start), "window_through": str(end),
                "retrieval_complete": retrieval_complete, "processing_issues": issues,
            }, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", default="recent_downloads")
    parser.add_argument("--check-connection", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        with connect_database() as connection:
            if args.check_connection:
                try:
                    for table in ("companies", "runs", "publications", "notifications", "mail_batches"):
                        # Fixed internal table names; never supplied by the user.
                        connection.execute(f"SELECT * FROM scanner.{table} LIMIT 0")
                except Exception:
                    raise DatabaseError("DB_SCHEMA: verbinding geslaagd, maar scannertabellen of leesrechten ontbreken. Controleer de SQL-migratie en rolrechten.") from None
                print("Databaseverbinding en leesrechten op scannertabellen gecontroleerd")
                return 0
            import tender_scan
            did_run = run_scan(tender_scan, Store(connection), config, args.output_dir,
                               datetime.now(ZoneInfo("Europe/Amsterdam")).date(),
                               scheduled=os.environ.get("RESPECT_SCHEDULE", "false").lower() == "true",
                               send_email=os.environ.get("SEND_EMAIL", "false").lower() == "true",
                               github_url=os.environ.get("RUN_URL", ""))
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                    output.write(f"did_run={str(did_run).lower()}\n")
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, (IncompleteRetrieval, DatabaseError, ValueError)) else f"Database-scan mislukt ({type(exc).__name__}); raadpleeg runstatus"
        print(message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
