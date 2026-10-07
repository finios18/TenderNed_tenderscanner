# TenderNed Data & Detachering Tender Scanner

Automated TenderNed scanner that searches recent Dutch public tenders, filters them by relevant CPV codes, downloads tender documents, scans PDFs and ZIP archives for recruitment/data-related keywords, identifies the main procurement guide (*leidraad*), and optionally performs an AI-based commercial fit assessment.

## Features

- Fetches recent TenderNed publications
- Filters tenders using configurable CPV whitelists
- Supports:
  - PDF documents
  - ZIP archives containing PDFs
  - Nested ZIP archives (optional)
- Searches documents for predefined keywords such as:
  - Data Engineer
  - Data Scientist
  - Azure
  - Python
  - Detachering
  - Personeelsinhuur
  - Power BI
  - DevOps
- Automatically detects likely procurement guides (*leidraad*)
- Optional OpenAI analysis of the detected lead document
- Robust networking with retries and timeout protection
- PDF parsing watchdog prevents hanging processes
- Generates structured JSON assessments for promising tenders

---

## Workflow

```text
TenderNed API
       │
       ▼
Recent Publications
       │
       ▼
CPV Filter
       │
       ▼
Download Documents
(PDF / ZIP)
       │
       ▼
Keyword Detection
       │
       ▼
Leidraad Identification
       │
       ▼
Optional OpenAI Analysis
       │
       ▼
GO / MAYBE / NO_GO Assessment
```

---

## Installation

### Clone repository

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

### Install dependencies

```bash
pip install requests python-dateutil PyPDF2 pdfminer.six openai
```

---

## OpenAI Setup (Optional)

To enable AI analysis:

```bash
export OPENAI_API_KEY="your_api_key"
```

Windows:

```cmd
set OPENAI_API_KEY=your_api_key
```

Optional:

```bash
export OPENAI_MODEL=gpt-5.4-mini
```

---

## Usage

### Basic scan

```bash
python tender_scan_with_filters_4.py
```

### Scan last 7 days

```bash
python tender_scan_with_filters_4.py --days 7
```

### Enable OpenAI evaluation

```bash
python tender_scan_with_filters_4.py --analyze_openai
```

### Follow nested ZIP archives

```bash
python tender_scan_with_filters_4.py --zip_follow_nested
```

### Full example

```bash
python tender_scan_with_filters_4.py \
    --days 7 \
    --pages 20 \
    --analyze_openai \
    --zip_follow_nested
```

---

## Command Line Arguments

| Argument | Description |
|-----------|------------|
| `--days` | Number of days to scan back |
| `--pages` | Maximum TenderNed result pages |
| `--download_dir` | Output folder |
| `--throttle` | Delay between downloads |
| `--zip_max_mb` | Maximum ZIP size to process |
| `--zip_follow_nested` | Process ZIP files inside ZIP files |
| `--analyze_openai` | Enable OpenAI tender assessment |
| `--openai_model` | OpenAI model to use |

---

## CPV Filtering

The scanner only processes tenders matching a predefined whitelist of CPV codes.

Examples include:

- IT Services
- Software Development
- Data Services
- Recruitment Services
- Temporary Staffing
- Personnel Supply Services
- Business Consultancy

The whitelist can be modified in:

```python
CPV_WHITELIST_RAW
```

---

## Keyword Detection

The content keywords also include detachering, personeelsinhuur,
terbeschikkingstelling, recruitment, data governance and data stewardship.

All recorded skip reasons are saved to `<download_dir>/overgeslagen_overzicht.json`
and shown in the terminal. Events include date/CPV/content filters, missing
documents or download links, unsupported types, PDF failures/timeouts, ZIP size,
format and entry problems, disabled nested ZIP processing, missing lead documents,
disabled/failed AI analysis and MAYBE/NO_GO outcomes. API failures and reaching
the configured page limit are also recorded. An event includes the publication
and document context where available; CPV-rejected publications do not fetch
document lists. The report describes the current run and is saved even if the
scan raises an exception after starting. The existing missing-lead-document
report remains available separately. Both JSON files are included in the
GitHub Actions download artifact.

The script searches document text for keywords including:

```text
inhuur
detachering
data engineer
data scientist
data architect
power bi
azure
aws
python
devops
software developer
it architect
data-specialist
personeelsinhuur
```

Keywords are configured in:

```python
KEYWORDS
```

---

## Tender Document Detection

The current entry point is `tender_scan.py`. Procurement document titles are
matched case-insensitively against `AANBESTEDING_KEYWORDS`, including bestek,
inkoopdocument, selectiedocument, uitnodiging tot inschrijving, tender document,
inleiding, omschrijving and uti. Existing lead-document terms remain supported.
Specific lead-document titles rank above the generic terms inleiding, omschrijving
and uti. These title keywords are separate from the IT/data content keywords.

After a content keyword hit, publications without a detected lead-document PDF
are listed in the terminal and saved to
`<download_dir>/overgeslagen_zonder_leidraad.json`. The report contains publication
ID, title, organisation, publication date and document names/types, including
unsupported documents, documents without download links and encountered ZIP
entries. These publications receive no AI assessment. Publications skipped by
CPV or content keyword filters are outside this report. The JSON describes the
latest completed scan and is overwritten on the next completed scan, including
when no publications were skipped. It is also included in the workflow's
download artifact.

After a tender passes:

1. Publication filter
2. CPV filter
3. Keyword filter

the script attempts to identify the main procurement document (*leidraad*) using document title matching.

Examples:

- Leidraad
- Inschrijfleidraad
- Beschrijvend document
- Aanbestedingsdocument
- Offerteaanvraag

---

## AI Tender Assessment

The workflow emails one readable `GO-aanbestedingen.html` attachment instead of
raw JSON files. It contains an overview table and per-tender sections for the
commercial conclusion, client, deadline, value, contract, roles, requirements,
risks, award criteria, planning and advice. Missing values show as “Onbekend”.
Open the attachment in a browser. The mail subject includes the GO count and
the body links to the full download artifact. With no GO results, the email
has no attachment.

The scanner writes `current_scan_results.json` containing only AI results from
the current run. `go_mail_report.py` generates the mail from this file; historical
GO folders are not included. This formatting step does not call OpenAI. Original
analysis JSONs and raw responses remain in the download artifact, alongside the
HTML summary. The workflow creates the summary before uploading the artifact.

When enabled, the script uploads the detected lead document to OpenAI and requests a structured evaluation.

Possible outcomes:

- `GO`
- `MAYBE`
- `NO_GO`

The evaluation considers:

- Detachering suitability
- Personnel supply relevance
- Data and IT relevance
- Commercial fit
- Contract type
- Estimated contract value
- Knockout risks

Results are stored as JSON files in the publication folder.

---

## Output Structure

```text
recent_downloads/
│
├── 123456/
│   ├── document1.pdf
│   ├── document2.pdf
│   └── openai_analysis_123456.json
│
├── 123457/
│   └── ...
```

---

## Example Output

```text
[123456] Municipality Data Platform Framework Agreement

CPV match found
Documents downloaded
Keywords found:
- data engineer
- azure
- detachering

Leidraad detected:
- Inschrijfleidraad.pdf

OpenAI verdict:
GO
Confidence: 92
```

---

## Disclaimer

This project is intended for procurement opportunity discovery and commercial tender qualification. Results generated by keyword matching and AI analysis should always be reviewed by a human before making business decisions.

---

## Why this exists

This tool was built to automate the discovery and qualification of Dutch public-sector staffing and data-related tenders. It reduces the manual effort required to review hundreds of TenderNed publications by combining CPV filtering, document analysis, and AI-assisted qualification.
