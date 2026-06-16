# TenderNed Data & Detachering Tender Scanner

Automated TenderNed scanner that searches recent Dutch public tenders, filters them by relevant CPV codes, downloads tender documents, scans PDFs and ZIP archives for recruitment/data-related keywords, identifies the main procurement guide (*leidraad*), and optionally performs an AI-based commercial fit assessment.

## Features

- Fetches recent TenderNed publications
- Filters tenders using configurable CPV whitelists
- Supports:
  - PDF documents
  - ZIP archives containing PDFs
  - Nested ZIP archives (optional)
- Searches documents for predefined keywords
- Automatically detects likely procurement guides (*leidraad*)
- Optional OpenAI analysis of the detected lead document
- Robust networking with retries and timeout protection
- PDF parsing watchdog prevents hanging processes
- Generates structured JSON assessments for promising tenders

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

## Installation

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
pip install requests python-dateutil PyPDF2 pdfminer.six openai
```

## OpenAI Setup

```bash
export OPENAI_API_KEY="your_api_key"
```

Windows:

```cmd
set OPENAI_API_KEY=your_api_key
```

## Usage

Basic scan:

```bash
python tender_scan_with_filters_4.py
```

Scan last 7 days:

```bash
python tender_scan_with_filters_4.py --days 7
```

Enable AI evaluation:

```bash
python tender_scan_with_filters_4.py --analyze_openai
```

## CPV Filtering

The scanner only processes tenders matching a predefined whitelist of CPV codes covering:

- IT Services
- Software Development
- Data Services
- Recruitment Services
- Temporary Staffing
- Business Consultancy

## AI Assessment

Possible outcomes:

- GO
- MAYBE
- NO_GO

The evaluation considers:

- Detachering suitability
- Personnel supply relevance
- Data and IT relevance
- Commercial fit
- Contract type
- Estimated contract value
- Knockout risks

## Why this exists

This tool was built to automate the discovery and qualification of Dutch public-sector staffing and data-related tenders. It reduces the manual effort required to review hundreds of TenderNed publications by combining CPV filtering, document analysis, and AI-assisted qualification.
