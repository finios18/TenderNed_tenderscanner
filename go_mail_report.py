"""Maak een leesbare mailbijlage uit GO-resultaten van de huidige scan."""
import argparse
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def display(value):
    return escape(str(value)) if value is not None and value != "" else "Onbekend"


def bullets(values):
    if not values:
        return "<p>Onbekend</p>"
    if not isinstance(values, list):
        values = [values]
    return "<ul>" + "".join(f"<li>{display(value)}</li>" for value in values) + "</ul>"


def euros(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "€ " + f"{value:,.0f}".replace(",", ".")
    return display(value)


def render_html(results, run_url=""):
    rows, cards = [], []
    for index, result in enumerate(results, 1):
        analysis = result["analysis"]
        summary = analysis.get("summary") or {}
        title = result.get("publication_title")
        client = analysis.get("client") or result.get("organisation")
        deadline = analysis.get("submission_deadline")
        value = euros(analysis.get("estimated_total_value_eur"))
        rows.append(f'<tr><td><a href="#go-{index}">{display(title)}</a></td><td>{display(client)}</td><td>{display(deadline)}</td><td>{value}</td></tr>')
        fields = [
            ("Opdrachtgever", display(client)), ("Inschrijfdeadline", display(deadline)),
            ("Opdrachtwaarde", value), ("Contractvorm", display(analysis.get("contract_type"))),
            ("Looptijd", display(analysis.get("contract_duration"))),
            ("Aantal leveranciers", display(analysis.get("number_of_suppliers"))),
        ]
        facts = "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in fields)
        sections = [
            ("Waarom GO?", f'<p>{display(analysis.get("reason_short"))}</p>'),
            ("Opdracht", f'<p>{display(summary.get("opdracht") or analysis.get("main_scope"))}</p>'),
            ("Scope", f'<p>{display(summary.get("scope") or analysis.get("main_scope"))}</p>'),
            ("Gevraagde functies", bullets(analysis.get("relevant_roles_found"))),
            ("Belangrijkste eisen", bullets(summary.get("belangrijkste_eisen"))),
            ("Knock-out-risico’s", bullets(analysis.get("knockout_risks"))),
            ("Gunning", f'<p>{display(summary.get("beoordeling_en_gunning"))}</p>'),
            ("Planning", f'<p>{display(summary.get("planning"))}</p>'),
            ("Advies", f'<p>{display(summary.get("advies") or analysis.get("commercial_fit"))}</p>'),
        ]
        content = "".join(f"<h3>{label}</h3>{text}" for label, text in sections)
        cards.append(f'<article id="go-{index}"><span class="badge">GO</span><h2>{display(title)}</h2><p class="muted">Publicatie-ID: {display(result.get("publication_id"))}</p><dl>{facts}</dl>{content}</article>')
    generated = datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%d-%m-%Y %H:%M")
    documents = f'<p><a href="{escape(run_url, quote=True)}">Open de scan en download de volledige aanbestedingsdocumenten</a></p>' if run_url else ""
    return f'''<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GO-aanbestedingen</title><style>
body{{font:16px/1.6 Arial,sans-serif;color:#223047;background:#f1f5f9;margin:0;padding:32px}}main{{max-width:1050px;margin:auto}}
h1,h2,h3{{line-height:1.3}}h3{{font-size:17px;margin-bottom:6px}}article,.overview{{background:white;border:1px solid #dbe3ed;border-radius:12px;padding:28px;margin:24px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #dbe3ed;vertical-align:top;overflow-wrap:anywhere}}th{{background:#edf3fa}}
a{{color:#125ca5}}.badge{{background:#d8f5e5;color:#11643b;padding:5px 12px;border-radius:20px;font-weight:bold}}.muted{{color:#58677b}}
dl{{display:grid;grid-template-columns:180px 1fr;gap:8px 16px;background:#f5f8fc;padding:18px}}dt{{font-weight:bold}}dd{{margin:0}}p,li,dd{{overflow-wrap:anywhere}}
@media(max-width:650px){{body{{padding:12px}}article,.overview{{padding:16px}}dl{{grid-template-columns:1fr}}.table-wrap{{overflow-x:auto}}}}
@media print{{body{{background:white;padding:0}}article{{break-before:page;border:none;padding:0}}a{{color:inherit}}}}
</style></head><body><main><h1>GO-aanbestedingen</h1><p>{len(results)} interessante aanbestedingen · Scanoverzicht van {generated} (Nederlandse tijd)</p>
{documents}<section class="overview"><h2>Overzicht</h2><div class="table-wrap"><table><thead><tr><th>Aanbesteding</th><th>Opdrachtgever</th><th>Deadline</th><th>Opdrachtwaarde</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
{"".join(cards)}<p class="muted">Deze samenvatting is gebaseerd op de AI-beoordeling van de geselecteerde leidraad. Onbekend betekent dat geen informatie beschikbaar is in die beoordeling.</p>
</main></body></html>'''


def create_mail_report(results, output_dir, run_url=""):
    go_results = [result for result in results if result.get("status") == "OK"
                  and isinstance(result.get("analysis"), dict)
                  and str(result["analysis"].get("decision", "")).strip().upper() == "GO"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    attachment = output_dir / "GO-aanbestedingen.html"
    count = len(go_results)
    subject = f"TenderNed: {count} GO-aanbestedingen gevonden"
    if count:
        attachment.write_text(render_html(go_results, run_url), encoding="utf-8")
        message = f"TenderNed scan afgerond.\n\nEr zijn {count} GO-aanbestedingen gevonden.\nDe overzichtelijke samenvatting staat in de HTML-bijlage; open deze in een browser."
    else:
        attachment.unlink(missing_ok=True)
        message = "TenderNed scan afgerond.\n\nEr zijn in deze scan geen GO-aanbestedingen gevonden."
    if run_url:
        message += f"\n\nVolledige documenten en scanresultaten downloaden:\n{run_url}"
    (output_dir / "mail_summary.txt").write_text(message + "\n", encoding="utf-8")
    return {"subject": subject, "attachments": attachment.as_posix() if count else "", "count": count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output_dir", default="recent_downloads")
    parser.add_argument("--run_url", default="")
    args = parser.parse_args()
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise ValueError("Scanresultaten moeten een JSON-lijst zijn")
    metadata = create_mail_report(results, args.output_dir, args.run_url)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for key, value in metadata.items():
                output.write(f"{key}={value}\n")
    print(f"Mailoverzicht gemaakt: {metadata['count']} GO-aanbestedingen")


if __name__ == "__main__":
    main()
