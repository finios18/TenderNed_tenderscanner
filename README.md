# TenderNed Data & Detachering Tender Scanner

## Databasevoortgang instellen (nieuwe, optionele route)

Alle bedrijfsworkflows gebruiken standaard **de databasevariant**, zowel
handmatig als gepland. Dit geldt voor Jan Snel, Weekly Tender Scan (HoB) en
Company Tender Scan. De generieke workflow heeft geen database-aan/uitkeuze
meer; `check_database_only` blijft beschikbaar voor verbindingstests.
Voor een volgend bedrijf moeten database en secrets vooraf zijn ingericht;
de scanner maakt geen Supabase-projecten, tabellen of secrets automatisch aan.

### Eenmalige inrichting in Supabase en GitHub

1. Gebruik je bestaande Supabase/PostgreSQL-project of maak een project aan.
2. Open de SQL Editor als databasebeheerder en voer `database/001_scanner.sql`
   één keer uit. Dit maakt een apart, privé `scanner`-schema en een beperkte
   `scanner_worker`-rol. Voeg dit schema **niet** toe aan de exposed API schemas.
   De bestaande website-tabellen worden niet aangepast.
3. Kies zelf een sterk wachtwoord en voer afzonderlijk uit:

   ```sql
   ALTER ROLE scanner_worker LOGIN PASSWORD '<jouw-eigen-wachtwoord>';
   ```

   Vervang de placeholder lokaal in de SQL Editor. Zet het echte wachtwoord niet
   in een bestand, commit, chatbericht of Actions-log.
4. Open in Supabase **Connect → Session pooler**. Gebruik de weergegeven host,
   database en poort, maar verander de gebruiker van `postgres.<project-ref>`
   naar `scanner_worker.<project-ref>` en gebruik het gekozen scannerwachtwoord.
   Het URI-formaat is bijvoorbeeld:

   ```text
   postgresql://scanner_worker.PROJECT_REF:URL_ENCODED_PASSWORD@SESSION_POOLER_HOST:5432/postgres?sslmode=require
   ```

   Gebruik de echte waarden uit jouw project, inclusief de exacte poolerhost;
   URL-encode speciale tekens in het wachtwoord. Gebruik **session mode** of een
   directe PostgreSQL-verbinding, geen transaction pooler: de scanner gebruikt
   een sessiegebonden advisory lock per bedrijf. Voor certificaatverificatie
   ondersteunt de verbinding ook `sslmode=verify-full` met een CA-certificaat.
   Zie [Supabase-verbindingen](https://supabase.com/docs/guides/database/connecting-to-postgres).
5. Voeg in GitHub onder **Settings → Secrets and variables → Actions →
   Repository secrets** de volledige verbindingsstring toe als
   `SCANNER_DATABASE_URL`. Alle bedrijfsscans kunnen dit secret delen; de
   scannergebruiker is een vertrouwde backendrol met toegang tot alle
   scannerrijen. Bedrijfsscheiding in de scanner gebeurt via `company_id`.
   Websitegebruikers krijgen hiermee geen extra databasebevoegdheden.
6. Controleer in `profiles/jan-snel.json` het blok:

   ```json
   "retrieval": {
     "first_publication_date": "2026-11-24",
     "overlap_days": 2,
     "through": "yesterday"
   }
   ```

   Kies bewust de eerste gewenste publicatiedatum. De databasevariant scant
   volledige kalenderdagen in Europe/Amsterdam, tot en met gisteren. `scan.days`
   beperkt deze route niet. Gebruik geen aanvullende publicatie-/sluitingsdatum-
   API-filters in een profiel met `retrieval`; de validator weigert die combinatie.
7. Commit/push de implementatie en start **Actions → Company Tender Scan** met
   het profiel `profiles/jan-snel.json`, Environment `jan-snel`,
   en voor de eerste proef **send_email=false**. De database staat standaard aan.
   Inspecteer het artifact `database_run.json`, de publicatierapporten en de
   tabellen hieronder. Dit kan OpenAI-kosten maken als AI aanstaat.

Optioneel kun je lokaal alleen de verbinding en leesrechten controleren nadat je
het secret veilig als lokale omgevingsvariabele hebt ingesteld:

```sh
uv run --locked python database_scan.py --config profiles/jan-snel.json --check-connection
```

Dit kan ook zonder lokale secrets via **Actions → Company Tender Scan →
Run workflow → check_database_only=true**. Deze optie controleert alleen de
verbinding en leesrechten op de vijf scannertabellen; hij doet geen
TenderNed-, OpenAI- of mailaanroepen en wijzigt geen scanvoortgang.
Bij verbindingsfouten verschijnt een veilige foutcategorie (`DB_AUTH`,
`DB_USER`, `DB_PROJECT`, `DB_DNS`, `DB_TIMEOUT`, `DB_TLS`, enzovoort),
zonder oorspronkelijke drivertekst, wachtwoord of verbindingsstring te loggen.
Controleer bij `DB_AUTH` het wachtwoord van `scanner_worker`, bij
`DB_PROJECT` de combinatie projectreferentie/poolerhost en bij `DB_USER`
het gebruikersformaat `scanner_worker.PROJECT_REF`.

Nieuwe bedrijfsworkflows gebruiken standaard de database. Geef bij geplande
scans ook `respect_schedule: ${{ github.event_name == 'schedule' }}` mee.
Laat e-mail aan of uit via `send_email`. In de databasevariant verstuurt Python de mail met
SMTP_SSL op poort 465 of STARTTLS op andere poorten; de oude mailactie wordt
voor die route overgeslagen.

### Opgeslagen voortgang en foutafhandeling

| Tabel in schema `scanner` | Inhoud |
| --- | --- |
| `companies` | Eerste ophaaldatum, selectiehash, opgehaald t/m en laatste volledig afgeronde scandag |
| `runs` | Datumvenster, start/einde, GitHub-link en complete/incomplete/failed-status |
| `publications` | Publicatie- en documentmetadata, fingerprint, resultaat en retry-status |
| `notifications` | Unieke GO-resultaten per bedrijf, publicatie en fingerprint; koppeling aan mailbatch |
| `mail_batches` | Ontvanger, rapportinhoud en prepared/sending/sent-status |

De ophaaldatum schuift pas door nadat alle pagina's én benodigde metadata
succesvol zijn opgeslagen. Ontbrekende `totalElements`, ongeldige responses,
dubbele ID's, veranderende aantallen, API-fouten en paginalimieten blokkeren dat.
Een databasefout leidt tot een mislukte run, nooit tot een stateloze terugval.
Gedeeltelijk opgeslagen publicaties blijven beschikbaar voor de volgende poging.

Document-/AI-fouten, ontbrekende documenten en ontbrekende leidraden blijven als
retry staan. Herpogingen hebben oplopende wachttijd (1 tot maximaal 24 uur),
zonder vaste maximale pogingentelling. Permanente onleesbaarheid kan dus de
scanstatus onvolledig houden. Deze publicaties moeten handmatig onderzocht worden.
Een zuivere CPV-/keyword-afwijzing is afgerond. Geldige GO/MAYBE/NO_GO-beoordelingen
worden opgeslagen. GO's gaan naar de mailwachtrij, ook als mailen tijdens een
proef uitstaat; later mailen stuurt die nog niet verstuurde GO's alsnog.

De dagelijkse planning bepaalt het meest recente geplande moment vanaf
`start_date`, met stappen van `interval_days`. Als dat moment nog niet succesvol
is afgehandeld, wordt gescand. Achterstallige scans worden dagelijks opnieuw
geprobeerd. Een herstelrun op maandag verschuift de volgende zondagscan niet;
ook een handmatige uitvoering verschuift het ingestelde ritme niet. Een
sessiegebonden databaselock voorkomt dubbele gelijktijdige runs voor hetzelfde
bedrijf, ook vanuit verschillende workflows. Een gestopte verbinding geeft deze
lock automatisch vrij.

De fingerprint omvat publicatiedetails, documentlijst en bedrijfsselectie/prompt.
Ongewijzigde, afgeronde publicaties worden niet opnieuw geanalyseerd. Wijzig je
API-filters, inhoudsfilters, prompt, AI-instellingen of eerste ophaaldatum, dan
begint de databasevariant opnieuw bij `first_publication_date`. Dit kan nieuwe
AI-kosten en nieuwe rapportages opleveren. Bij gewijzigde documentmetadata wordt
de publicatie opnieuw verwerkt. Onzichtbare bestandswijzigingen zonder gewijzigde
metadata worden niet gegarandeerd ontdekt; binaries worden niet onbeperkt in de
database bewaard. Publicaties die buiten de overlap alsnog zichtbaar worden,
vereisen een bewuste ruimere hercontrole.

### Mail met onzekere afleverstatus herstellen

SMTP biedt geen gegarandeerde exactly-once-aflevering. Vóór verzending zet de
scanner de batch op `sending`; pas na acceptatie door SMTP wordt dit `sent`.
Bij een timeout/crash rond verzending blijft `sending` staan en blokkeert
automatisch opnieuw mailen. Controleer in de mailproviderlogs of het bericht met
Message-ID `<tenderscanner-BATCH_ID@tenderscanner.local>` is geaccepteerd.
Bevestig daarna in de SQL Editor **één van beide** uitkomsten:

```sql
-- Bericht is aantoonbaar verstuurd:
UPDATE scanner.mail_batches SET status='sent', sent_at=now()
WHERE batch_id='CONTROLEER-EERST-DE-ECHTE-BATCH-UUID' AND status='sending';

-- OF: bericht is aantoonbaar niet verstuurd; sta een nieuwe poging toe:
UPDATE scanner.mail_batches SET status='prepared'
WHERE batch_id='CONTROLEER-EERST-DE-ECHTE-BATCH-UUID' AND status='sending';
```

Voer niet beide statements uit. Een voorbereide batch houdt zijn ontvanger vast;
bij een gewijzigd MAIL_TO moet je die batch eerst bewust controleren/aanpassen.

### Databasevariant testen

De gewone tests gebruiken geen productie-database. De workflow **Scanner Tests**
start een wegwerp-PostgreSQL 16-database en test migratie, beperkte rechten, locks,
deduplicatie, retries en mailregistratie. Die workflow is ook handmatig te starten.
Lokaal worden deze integratietests overgeslagen tenzij `TEST_SCANNER_ADMIN_URL`
is ingesteld op een expliciet daarvoor bedoelde database met een naam eindigend
op `_test`. De integratietests wissen het `scanner`-schema in die testdatabase.
Gebruik dit secret nooit voor een gewone of productie-database.

## Bedrijfsprofielen en nieuwe Actions-scans

Onderzocht op 24 november 2026. De scanner ondersteunt nu `--config` met een
apart JSON-profiel en een los promptbestand per bedrijf. De bestaande
`weekly-tender-scan.yml` blijft zijn huidige instellingen gebruiken. Hetzelfde
bedrijfsprofiel is beschikbaar als `profiles/hob.json` en `prompts/hob.txt`.

### Nieuwe scan zelf invullen

1. Kopieer `profiles/jan-snel.json` en `prompts/jan-snel.txt` naar een
   eigen bedrijfsnaam. Pas `id` en `prompt_file` aan. Het promptpad is relatief
   aan het JSON-bestand.
2. Vul in `api` de TenderNed-filters in. Vul in `filters` de CPV-whitelist,
   documentzoekwoorden in. Leidraadtitels en hun prioriteit staan voor alle
   bedrijven centraal in `AANBESTEDING_KEYWORDS` in `tender_scan.py`.
   De drie filtergroepen `publicatieType`, `typeOpdracht` en
   `nationaalOfEuropees` gebruiken per code `true`/`false`, bijvoorbeeld:

   ```json
   "publicatieType": {
     "MAC": false,
     "VAK": true,
     "AAO": true,
     "REC": true,
     "AGO": false,
     "AAW": false
   }
   ```

   Alleen codes met `true` worden meegestuurd. Als binnen een groep alles
   `false` is, wordt die parameter weggelaten: alle opties zijn dan mogelijk.
   Codes worden niet automatisch toegevoegd; ook VBE is alleen actief als je
   expliciet `"VBE": true` toevoegt. De overige meerkeuzefilters gebruiken lijsten.
   Lege API-lijsten betekenen geen beperking; lokale CPV- en zoekwoordenlijsten
   moeten gevuld zijn. CPV-match is exact op acht cijfers, geen automatische
   subcode-uitbreiding. Zoekwoorden werken als OF, hoofdletterongevoelig.
3. Vul het promptbestand met bedrijfsprofiel, gewenste opdrachten, waardegrenzen
   en beslisregels. Behoud het JSON-antwoordmodel voor de rapportgenerator.
   De velden `is_detachering_or_inhuur` en `value_within_80000000` zijn legacy;
   voor andere bedrijven hoeven ze geen beslisvoorwaarden te zijn.
4. Controleer lokaal:

   ```sh
   uv run --locked python tender_scan.py --config profiles/jan-snel.json --validate-config
   ```

5. Maak onder GitHub Settings > Environments een Environment per bedrijf.
   Stel daar `OPENAI_API_KEY`, `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`,
   `SMTP_PASSWORD` en `MAIL_TO` in waar nodig. Zet klantgebonden waarden op
   Environment-niveau; ontbrekende waarden kunnen anders terugvallen op
   bestaande repository-secrets. Stop secrets en ontvangers niet in profielbestanden.
6. Commit/push de bestanden. Kies Actions > Company Tender Scan > Run workflow,
   geef het configuratiepad op en kies het Environment. E-mail is standaard uit.
   Bij een nieuw gekopieerd profiel zet je `scan.analyze_openai` pas op `true`
   nadat je de bedrijfsprompt hebt ingevuld. Bij Jan Snel staat AI inmiddels aan.
   Zonder AI zijn er geen AI-GO-resultaten.

Een profiel bevat `schema_version`, `id`, `api`, `filters`, `scan`, `prompt_file`.
De `scan`-opties zijn `days`, `pages`, `throttle`, `zip_max_mb`,
`zip_follow_nested`, `analyze_openai` en optioneel `openai_model`.
Bestaande CLI-opties overschrijven de profielwaarden. Paginagrootte is momenteel
vast 50; `pages` bepaalt het maximum aantal pagina's. Zonder `--config` blijft
de bestaande bediening beschikbaar.

### Een aparte geplande workflow per bedrijf

Ieder bedrijf krijgt een eigen aanroepbestand met een eigen `schedule` en
Environment. Voor Jan Snel staat dit klaar in
`.github/workflows/jan-snel-tender-scan.yml`: dagelijks om 07:15 Nederlandse tijd
wordt gecontroleerd of het bedrijf aan de beurt is. Het bedrijfsprofiel blijft
`profiles/jan-snel.json`. Stel daarin de frequentie in:

```json
"schedule": {
  "enabled": true,
  "interval_days": 3,
  "start_date": "2026-11-24"
}
```

`interval_days` mag 1, 2, 3, 7 of 14 zijn. De startdatum is de eerste scandag;
daarna volgen startdatum + N dagen, + 2N dagen, enzovoort. Bij 7 dagen bepaalt
de startdatum dus de weekdag. `enabled: false` schakelt geplande scans uit.
Handmatig starten omzeilt de planning. Jan Snel staat standaard op dagelijks (1).
De databasevariant haalt vanaf het opgeslagen eindpunt opnieuw op met
`retrieval.overlap_days` overlap, tot en met gisteren. `scan.days` is alleen
nog van toepassing bij rechtstreeks gebruik van de oude `tender_scan.py`-CLI.
Nieuwe bedrijfsworkflows kunnen dezelfde dagelijkse trigger en
`respect_schedule: ${{ github.event_name == 'schedule' }}` gebruiken bij de
aanroep van de herbruikbare workflow. Alleen op een scandag starten de
documentdownloads, AI-analyse en rapportage; de dagelijkse controle zelf is
een kleine Actions-job.
Mailen en AI-analyse staan voor Jan Snel aan. Bij de generieke handmatige
workflow is mailen standaard uit, zodat je een eerste proef zonder e-mail kunt doen.

Het interval staat in het bedrijfsprofiel, het tijdstip in de bedrijfsworkflow:

| Gewenste frequentie | Planning | Overlap bovenop opgeslagen voortgang |
| --- | --- | --- |
| Dagelijks | Dagelijkse controle plus profielinterval 1 | 2 dagen |
| Iedere 2 dagen | Dagelijkse controle plus profielinterval 2 | 2 dagen |
| Iedere 3 dagen | Dagelijkse controle plus profielinterval 3 | 2 dagen |
| Wekelijks | Dagelijkse controle plus profielinterval 7, startdatum op gewenste weekdag | 2 dagen |
| Iedere 14 dagen | Dagelijkse controle plus profielinterval 14 | 2 dagen |

De intervalcontrole werkt over maand- en jaargrenzen heen. Gebruik hiervoor
geen `*/2`, `*/3` of `*/14` in het dag-van-de-maandveld: dit begint bij iedere
nieuwe maand opnieuw en vormt geen doorlopend interval. De frequentie uit de
website-export moet momenteel handmatig worden overgenomen als `interval_days`.
Een profielwijziging wijzigt de effectieve scandagen, niet de dagelijkse cron.
De databasevoortgang zorgt dat gemiste/mislukte perioden worden ingehaald.

GitHub ondersteunt `timezone: Europe/Amsterdam` naast `cron` zodat een gekozen
Nederlandse tijd ook bij zomer-/wintertijd gelijk blijft. Zonder `timezone`
geldt UTC. Zie de
[officiële schedule-documentatie](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Geplande uitvoeringen kunnen vertraagd starten; cron is geen garantie voor een
exact begintijdstip. De databasevariant dedupliceert afgeronde publicaties.

De handmatige workflow is al toegevoegd. Voor een eigen planning maak je een
klein bestand in `.github/workflows/` dat de gedeelde workflow aanroept:

```yaml
name: Scan Mijn Bedrijf
on:
  workflow_dispatch:
  schedule:
    - cron: "15 7 * * *"
      timezone: Europe/Amsterdam
permissions:
  contents: read
concurrency:
  group: scan-mijn-bedrijf
  cancel-in-progress: false
jobs:
  scan:
    uses: ./.github/workflows/reusable-tender-scan.yml
    with:
      config: profiles/mijn-bedrijf.json
      environment: mijn-bedrijf
      send_email: true
      respect_schedule: ${{ github.event_name == 'schedule' }}
      use_database: true
    secrets: inherit
```

De cron hierboven controleert dagelijks om 07:15 Nederlandse tijd of het
bedrijf aan de beurt is. Vul in ieder profiel `schedule` en `retrieval` in.
Elke job heeft een
eigen runner en het artifact krijgt het Environment in zijn naam. Infrastructuur,
documentverwerking en e-mailopmaak worden gedeeld via de herbruikbare workflow.
HoB staat op zondag met startdatum 29 november 2026, dagelijkse controle om 02:15,
eerste ophaaldatum 21 november 2026 en twee dagen overlap. Bij de eerste run
wordt die initiële periode opnieuw beoordeeld; eerdere stateloze beoordelingen
zijn niet automatisch in de database geïmporteerd. HoB gebruikt Environment
`hob` en valt voor ontbrekende Environment-secrets terug op repository-secrets,
inclusief de bestaande `MAIL_TO`. Een eigen `MAIL_TO` kan later in `hob` worden gezet.

### Onderzoek: TenderNed PAPI

De openbare JSON-publicatiewebservice staat op
`https://www.tenderned.nl/papi/tenderned-rs-tns/v2`.
Dit is de service die deze scanner gebruikt. De overheid waarschuwt dat de
webservice zonder voorafgaande kennisgeving kan veranderen
([datasetbeschrijving](https://data.overheid.nl/dataset/aankondigingen-van-overheidsopdrachten---tenderned)).
De [officiële Swagger](https://www.tenderned.nl/info/swagger/) documenteert de
XML-interface `GET /publicaties/{publicatieId}/public-xml`, met Basic Auth,
aan te vragen via functioneelbeheer@tenderned.nl. Deze XML-interface levert
publicaties vanaf 4 april 2018 en is geen documentatie van alle JSON-zoekfilters.

De onderstaande lijst bevat alle 20 queryparameters die de officiële frontend
bij `getPublicaties` opbouwt, gecontroleerd in de
[zoekmodule 4244](https://www.tenderned.nl/aankondigingen/4244.b397d72c1b9e555a.js)
van het [aankondigingenplatform](https://www.tenderned.nl/aankondigingen/overzicht).
Dit is een volledige inventarisatie van die frontend-aanroep, geen garantie dat
er geen andere interne/backendparameters bestaan. De filterwerking is uit de
officiële broncode afgeleid; niet elke combinatie is live functioneel getest.

| Queryparameter | Mogelijkheden |
| --- | --- |
| `page` | Paginanummer vanaf 0; beheerd door scanner |
| `size` | Resultaten per pagina; scanner gebruikt 50; servermaximum niet vastgesteld |
| `search` | Zoektekst in aankondigingen; andere zoeklaag dan documentzoekwoorden |
| `sort` | Frontend biedt `relevantie` en `tappublicatiedatum`; scanner vereist de laatste |
| `publicatieType` | Lijst: MAC, VAK, AAO, REC, AGO, AAW; frontend voegt VBE toe bij AAO |
| `publicatieDatumPreset` | VDG vandaag, GST gisteren, AF7 afgelopen 7 dagen, AF30 afgelopen 30 dagen, AGP aangepaste periode |
| `publicatieDatumVanaf` | Begindatum, YYYY-MM-DD |
| `publicatieDatumTot` | Einddatum, YYYY-MM-DD |
| `nutsCodes` | Lijst geografische codes; volledige codelijst via `/nutscodes` |
| `typeOpdracht` | Lijst: D diensten, L leveringen, W werken |
| `nationaalOfEuropees` | Lijst: NL, EU |
| `aardVanDeOpdracht` | Lijst: OOP overheidsopdracht, OPD opdracht, RAA raamovereenkomst, ERK erkenningsregeling, CCO concessie, PRV prijsvraag, IDA instellen DAS |
| `procedure` | Lijst met procedurecodes, hieronder |
| `sluitingsDatumPreset` | VDG vandaag, MRN morgen, KM7 binnen 7 dagen, KM30 binnen 30 dagen, VMN volgende maand, AGP aangepast, TKM alle openstaande, ONB zonder sluitingsdatum |
| `sluitingsDatumVanaf` | Begindatum, YYYY-MM-DD |
| `sluitingsDatumTot` | Einddatum, YYYY-MM-DD |
| `typeAanbestedendeDienst` | Lijst met organisatietypen, hieronder |
| `aanbestedendeDienstId` | Lijst met opdrachtgever-ID's; opzoeken via `/aanbestedendediensten` |
| `cpvCodes` | Lijst CPV-codes; frontend gebruikt codewaarden uit CPV-selectie |

De profielconfiguratie ondersteunt alle genoemde filterparameters; `page` en
`size` beheert de scanner. Gebruik true/false-objecten voor `publicatieType`,
`typeOpdracht` en `nationaalOfEuropees`, en JSON-lijsten voor de overige
meerkeuzefilters. De actieve codes worden naar lijsten vertaald: requests
verstuurt ze als herhaalde queryparameters, bijvoorbeeld
`typeOpdracht=D&typeOpdracht=L`. Een lege lijst laat de parameter weg.
Bij een datumbereik kun je `AGP` meegeven. De lokale `scan.days`-controle blijft
altijd gelden: een ruimer of historisch API-datumbereik verruimt die niet.

Procedurecodes: OPE openbaar; NOP niet-openbaar; CCD concurrentiegerichte dialoog;
OMB mededinging met onderhandeling; OZB onderhandeling zonder voorafgaande oproep;
OHP onderhands; OH Open House; INP innovatiepartnerschap; CA concurrentiegerichte
aanbesteding; APM andere procedure in meerdere fasen; APE andere procedure in één
fase; VUB verzoek om uitdrukking van belangstelling (spoor).

Typen aanbestedende dienst: `cga` centrale overheid; `def-cont` defensiecontractant;
`spec-rights-entity` entiteit met bijzondere/uitsluitende rechten; `eu-ins-bod-ag`
Europese instelling/agentschap of internationale organisatie; `org-sub`
gesubsidieerde opdrachtgever; `pub-undert` overheidsonderneming; `body-pl`
publiekrechtelijke instelling; `ra` regionale of plaatselijke instantie.

Provinciekeuzes in de huidige frontend: NL13 Drenthe, NL23 Flevoland, NL12 Friesland,
NL22 Gelderland, NL11 Groningen, NL42 Limburg, NL41 Noord-Brabant, NL32 Noord-Holland,
NL21 Overijssel, NL35 Utrecht, NL34 Zeeland, NL36 Zuid-Holland; NL heel Nederland.
Gebruik voor een actuele volledige lijst het `/nutscodes`-endpoint.

De frontend gebruikt daarnaast de volgende GET-routes onder dezelfde `/v2`-basis:

| Route | Inhoud |
| --- | --- |
| `/publicaties` | Zoekresultaten met paginering |
| `/publicaties/{id}` | Publicatiedetails |
| `/publicaties/{id}/gerelateerd` | Gerelateerde publicaties |
| `/publicaties/{id}/html` | HTML van de aankondiging |
| `/publicaties/{id}/documenten` | Documentlijst met downloadlinks |
| `/publicaties/{id}/vragen-antwoorden` | Gepubliceerde vragen en antwoorden |
| `/publicaties/{id}/mededelingen` | Mededelingen |
| `/aanbestedendediensten?page=0&size=10&search=...` | Opdrachtgevers opzoeken |
| `/nutscodes` | Geografische codelijst |

Volg voor documentinhoud de downloadlink uit de documentenresponse; de scanner
doet dit al. De aparte RSS-route is `/papi/tenderned-rs-tns/rss/laatste-publicatie.rss`.
Er zijn geen bevestigde queryfilters voor bedrijfsgeschiktheid, omzet,
certificeringen, minimale/maximale opdrachtwaarde of een eigen AI-prompt in deze
frontend-aanroep. Zulke criteria horen in je lokale selectie en prompt.

### Advies voor klantinrichting

Gebruik API-filters voor brede afbakening, lokale CPV- en documentzoekwoorden
voor inhoudelijke selectie, en de prompt voor commerciële beoordeling. Een streng
API-zoekwoord of opdrachtvormfilter kan relevante tenders al uitsluiten voordat
de scanner de documenten leest. Begin breed en controleer de skiprapporten.
Een hoofdcode in de lokale CPV-lijst neemt subcodes niet vanzelf mee.

De bestaande website-export (`schema_version: 3`) is nog geen scannerprofiel.
Neem `scanner_config.cpv_whitelist` en `keywords` over naar `filters`, vertaal
de bedrijfscontext en commerciële wensen naar de prompt, en stel de planning
apart in Actions in. `email_frequency_days` plant zelf geen workflow en een
export met ontvangers hoort niet rechtstreeks als secretsbron te dienen.
Bij workflows met dagelijkse intervalcontrole neem je `email_frequency_days`
over als `schedule.interval_days`. Een automatische import/generator en
deduplicatie zijn mogelijke vervolgstappen.

Automated TenderNed scanner that searches recent Dutch public tenders, filters them by relevant CPV codes, downloads tender documents, scans PDFs and ZIP archives for recruitment/data-related keywords, identifies the main procurement guide (*leidraad*), and optionally performs an AI-based commercial fit assessment.

## Features

- Fetches recent TenderNed publications
- Filters tenders using configurable CPV whitelists
- Supports:
  - PDF documents
  - DOCX documents (paragraphs, tables, headers and footers)
  - ZIP archives containing PDFs and DOCX documents
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

### Install and synchronize with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once, then
run the following from the repository root:

```sh
uv sync --locked
```

uv manages Python 3.11 (pinned in `.python-version`) and the local `.venv`.
Manual activation is unnecessary: execute commands with `uv run --locked`.
Dependencies are declared in `pyproject.toml`; `uv.lock` records exact resolved
versions for reproducible installations locally and in GitHub Actions. Commit
both files, but do not commit `.venv` or the uv cache. `requirements.txt` is no
longer maintained or required.

```sh
uv run --locked python -m unittest discover -s tests -v
uv add package-name
uv remove package-name
uv lock --upgrade
uv sync --locked
```

When an external tool specifically requires pip requirements, generate an export
using `uv export --format requirements-txt --output-file requirements.txt` rather
than maintaining a second dependency list by hand.

### Project entry points

- `tender_scan.py`: current scanner used by the workflow, including DOCX support,
  central document-title priorities, skip reports and current-run AI results.
- `go_mail_report.py`: generates the readable GO mail attachment.

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
uv run --locked python tender_scan.py
```

### Scan last 7 days

```bash
uv run --locked python tender_scan.py --days 7
```

### Enable OpenAI evaluation

```bash
uv run --locked python tender_scan.py --analyze_openai
```

### Follow nested ZIP archives

```bash
uv run --locked python tender_scan.py --zip_follow_nested
```

### Full example

```bash
uv run --locked python tender_scan.py \
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
inleiding, omschrijving, uti, toelatingsdocument, aanbesteding and al.
This is the single ordered list used for lead-document recognition and priority:
the first matching term determines the score. Scores are not added together and
there are no negative terms or penalties. Move a term higher in the list to give
it higher priority. `al` is last, has score 1 and matches a standalone abbreviation
(such as `AL.pdf`), not a fragment of a word such as `algemeen`. Any other matching
term ranks above an AL-only document. These title keywords are separate from the
IT/data content keywords.

Both directly downloaded PDFs/DOCX files and those found inside ZIP archives
participate in content keyword matching and lead-document selection. DOCX text
is read using Python's standard library, including paragraphs, tables, headers
and footers. No extra dependency is needed. The same parser-worker timeout is
used for both formats. For an AI assessment, PDFs are uploaded as before; DOCX
content is sent as extracted text. Images and visual layout inside DOCX are not
included in the assessment. Legacy `.doc` files are not supported.

After a content keyword hit, publications without a detected lead-document PDF/DOCX
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

Each run also writes `geselecteerde_leidraden.csv` (Excel, semicolon-separated)
and `geselecteerde_leidraden.json` at the root of `recent_downloads/`. These list
the single selected lead document per publication, its title, publication,
organisation, file type, score, matched title terms, content keyword hits and
file path, plus the AI status and decision when available. Other candidates are
not listed as selected. The list includes NO_GO/MAYBE decisions, failed analyses
and selections made with AI disabled. An empty scan produces an empty report.
Paths reflect the final GO/Overig location. Both reports are included in the
`tender-results` GitHub artifact. Artifact upload is also attempted after a
failed scan; reports written on shutdown then contain the selections so far.

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
