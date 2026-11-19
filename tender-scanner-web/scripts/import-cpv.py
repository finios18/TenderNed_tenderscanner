"""Reproduceerbare CPV 2008-import uit de officiële Nederlandse PIANOo-XLSX.

Alleen Python 3.11+ standaardbibliotheek. Geen Excel-installatie nodig.
Gebruik: python scripts/import-cpv.py [--download] [--check]
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/cpv/source/pianoo_cpv.xlsx"
SOURCE_URL = "https://www.pianoo.nl/sites/default/files/media/documents/2022-07/overzicht_cpv_codes_simap.xlsx"
VERSION = "CPV 2008"
EXPECTED_COUNT = 9454
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_sheet(archive, filename, strings):
    rows = []
    for row in ET.fromstring(archive.read(filename)).findall(".//s:sheetData/s:row", NS):
        cells = {}
        for cell in row.findall("s:c", NS):
            column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
            value = cell.findtext("s:v", default="", namespaces=NS)
            if cell.attrib.get("t") == "s":
                value = strings[int(value)]
            elif cell.attrib.get("t") == "inlineStr":
                value = "".join(cell.itertext())
            cells[column] = value.strip()
        rows.append(cells)
    return rows


def parse_source(source=SOURCE):
    with zipfile.ZipFile(source) as archive:
        strings = ["".join(si.itertext()) for si in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rows = read_sheet(archive, "xl/worksheets/sheet1.xml", strings)
        supplementary = read_sheet(archive, "xl/worksheets/sheet2.xml", strings)
    entries = []
    for row in rows:
        code, description = row.get("A", ""), row.get("B", "")
        if code == "CODE":
            continue
        if not code and not description:
            continue
        if not re.fullmatch(r"\d{8}-\d", code) or not description:
            raise ValueError(f"Ongeldige bronrij: {row}")
        base = code[:8]
        precision = max(2, len(base.rstrip("0")))
        level = {2: "division", 3: "group", 4: "class", 5: "category"}.get(precision, "subcategory")
        entries.append({"code": code, "base_code": base, "description_nl": description,
                        "level": level, "precision": precision, "parent_code": None})
    entries.sort(key=lambda entry: entry["base_code"])
    by_base = {entry["base_code"]: entry for entry in entries}
    if len(entries) != EXPECTED_COUNT or len(by_base) != len(entries):
        raise ValueError(f"Verwacht {EXPECTED_COUNT} unieke basiscodes, gevonden {len(entries)}")
    for entry in entries:
        for length in range(entry["precision"] - 1, 1, -1):
            parent = by_base.get(entry["base_code"][:length].ljust(8, "0"))
            if parent:
                entry["parent_code"] = parent["code"]
                break
        if entry["level"] != "division" and entry["parent_code"] is None:
            raise ValueError(f"Geen bestaande bovenliggende code voor {entry['code']}")
    supplement_count = sum(bool(re.fullmatch(r"[A-Z]{2}\d{2}-\d", row.get("A", ""))) for row in supplementary)
    metadata = {"classification": VERSION, "language": "nl", "count": len(entries),
                "division_count": sum(e["level"] == "division" for e in entries),
                "source_url": SOURCE_URL, "source_page": "https://www.pianoo.nl/nl/regelgeving/cpv-codes",
                "structure_source": "https://ted.europa.eu/nl/simap/cpv",
                "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                "supplementary_count": supplement_count, "supplementary_included": False}
    return {"metadata": metadata, "entries": entries}


def sql_string(value):
    return "null" if value is None else "'" + value.replace("'", "''") + "'"


def generate_seed(dataset):
    metadata = dataset["metadata"]
    header = """-- Gegenereerd door scripts/import-cpv.py; niet handmatig wijzigen.
-- Nederlandse bron: PIANOo; classificatie en structuur: TED, CPV 2008.
begin;
create table public.cpv_catalog (
  code varchar(10) primary key check(code ~ '^[0-9]{8}-[0-9]$'),
  base_code varchar(8) not null unique check(base_code ~ '^[0-9]{8}$'),
  description_nl text not null check(length(description_nl)>0),
  level text not null check(level in ('division','group','class','category','subcategory')),
  precision smallint not null check(precision between 2 and 8),
  parent_code varchar(10) references public.cpv_catalog(code) deferrable initially deferred
);
create index cpv_catalog_parent on public.cpv_catalog(parent_code);
alter table public.cpv_catalog enable row level security;
create policy catalog_read on public.cpv_catalog for select to authenticated using(true);
revoke all on public.cpv_catalog from public,anon,authenticated;
grant select on public.cpv_catalog to authenticated;
grant all on public.cpv_catalog to service_role;
"""
    blocks = [header]
    entries = dataset["entries"]
    for start in range(0, len(entries), 500):
        rows = []
        for entry in entries[start:start+500]:
            rows.append("(" + ",".join([sql_string(entry["code"]), sql_string(entry["base_code"]),
                sql_string(entry["description_nl"]), sql_string(entry["level"]), str(entry["precision"]),
                sql_string(entry["parent_code"])]) + ")")
        blocks.append("insert into public.cpv_catalog(code,base_code,description_nl,level,precision,parent_code) values\n" + ",\n".join(rows) + ";\n")
    metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    blocks.append("create function public.get_cpv_catalog_info() returns jsonb language sql stable set search_path='' as $$ select " + sql_string(metadata_json) + "::jsonb $$;\nrevoke all on function public.get_cpv_catalog_info() from public,anon;\ngrant execute on function public.get_cpv_catalog_info() to authenticated;\ncommit;\n")
    return "\n".join(blocks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download de officiële XLSX opnieuw")
    parser.add_argument("--check", action="store_true", help="Controleer gegenereerde bestanden zonder ze te wijzigen")
    args = parser.parse_args()
    if args.download:
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Tenderprofiel CPV importer/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        # Valideer eerst; schrijf de bron alleen weg als de download echt een XLSX is.
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError("Download is geen CPV-werkboek")
        SOURCE.write_bytes(content)
    dataset = parse_source()
    outputs = {
        ROOT / "src/data/cpv-2008-nl.json": json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n",
        ROOT / "supabase/migrations/202611190002_cpv_catalog.sql": generate_seed(dataset),
    }
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Verouderd gegenereerd bestand: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps(dataset["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
