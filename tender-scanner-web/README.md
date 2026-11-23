# Tenderprofiel — afzonderlijke SaaS-PoC

Nederlandstalige website voor aanmelding en onboarding voor een gepersonaliseerde
TenderNed-scanner. Dit project voert de Python-scanner **niet** uit. De naam
Tenderprofiel en alle voorbeeldopdrachten zijn vervangbare pilotinhoud.

## Snel starten op Windows

Installeer [Node.js 22 LTS of nieuwer](https://nodejs.org/) en
[pnpm](https://pnpm.io/installation). Voer in PowerShell uit:

```powershell
cd C:\Users\finza\Documents\tenderscan_HoB\tender-scanner-web
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
# Vul .env.local met de publieke project-URL en publishable/anon key uit Supabase.
pnpm dev
```

Open http://127.0.0.1:3000. Zonder Supabase-configuratie werken de publieke pagina's;
accountacties tonen expliciet dat de omgeving nog niet is aangesloten. Er worden
geen accounts of opslag gesimuleerd in de echte applicatie.

Dit is een eigen projectmap met eigen dependencies en lockfile. De bovenliggende
Python-bestanden zijn niet gewijzigd. Voor een geheel aparte GitHub-repository:
kopieer alleen de inhoud van deze map (zonder node_modules, .next, out, .env.local
en testresultaten) naar een nieuwe directory en voer daar `git init` uit. De
website vereist geen uv; uv blijft voor de bestaande Python-scanner.

## Supabase inrichten

1. Maak in [Supabase](https://supabase.com/dashboard) een **Free** project aan.
   Kies bij voorkeur een EU-regio voor deze Nederlandse pilot. Bewaar het
   databasewachtwoord buiten Git.
2. Open SQL Editor en voer het volledige bestand
   `supabase/migrations/202611190001_initial.sql` één keer uit. Het is een
   versiegebonden migratie, geen herhaalbaar seed-script. Voer dit uit vóór de
   eerste registratie. De migratie maakt zeven tabellen, RLS, RPC's en een
   registratie-trigger aan. Maak in een bestaand project vooraf een back-up.
   Voer daarna ook `202611190002_cpv_catalog.sql` en
   `202611190003_cpv_selection.sql` en `202611230001_simplify_profile.sql` uit,
   in die volgorde. Voer in een bestaand project alleen de nog niet toegepaste migraties uit.
   De laatste migratie verwijdert de vervallen profielvelden en categorieën;
   publiceer aansluitend de bijbehorende websitecode.
   [CPV-upgrade en behoud van bestaande gegevens](docs/cpv.md).
3. Vul in `.env.local`:
   - `NEXT_PUBLIC_SUPABASE_URL`: de project-URL.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: de **publishable** key of legacy
     `anon` key. Dit is bewust een publieke browsersleutel, beschermd door RLS.
   - `NEXT_PUBLIC_PRIVACY_EMAIL`: het echte contactadres van de beheerder.
   Gebruik hier **nooit** een `service_role` of `sb_secret_…` key.
   De buildcontrole weigert zulke sleutels expliciet. Zonder beide variabelen
   kun je alleen de publieke preview bouwen.
4. Authentication → Providers → Email: email/password inschakelen, **Confirm
   email aan**, minimaal 12 tekens als wachtwoordbeleid. Anonymous sign-in uit.
5. Authentication → URL Configuration:
   - Lokaal Site URL: `http://127.0.0.1:3000`.
   - Toegestane redirect: `http://127.0.0.1:3000/auth/callback/`.
   - Voeg ook `http://127.0.0.1:3000/auth/callback/?next=password` toe.
   - Voeg na deployment dezelfde twee URL's op je exacte HTTPS-domein toe.
   Gebruik voor productie geen brede wildcard naar onbekende previewdomeinen.
6. Stel eigen **SMTP** in via Authentication → Email/SMTP voordat je externe
   testers uitnodigt. De ingebouwde Supabase-maildienst is beperkt en stuurt
   standaard alleen naar geautoriseerde teamadressen. Gebruik een bestaande
   SMTP-server of een provider binnen diens gratis limieten; er is geen
   mailprovider ingebouwd of betaald account aangemaakt.
7. Gebruik de standaard bevestigings-/hersteltemplates met `ConfirmationURL`.
   De app gebruikt PKCE en `/auth/callback/` wisselt de code één keer om. Open
   verificatie- en herstellinks in dezelfde browser als de aanvraag.
8. Herstart `pnpm dev` na wijzigingen aan `.env.local`.

Controleer de verbinding met `pnpm check:connection`. Deze alleen-lezen controle
verifieert de publieke sleutel, e-mailinstellingen en anonieme toegangsweigeringen
voor de acht tabellen en vier RPC's. Hij maakt geen account aan en verstuurt
geen mail. Succes bewijst nog niet dat inloggen en opslaan als gebruiker werken.

Je kunt migraties ook met de [Supabase CLI](https://supabase.com/docs/guides/cli)
beheren. De Dashboard SQL Editor-route vereist lokaal geen Docker. Voor een
volledig lokale Supabase-stack is Docker Desktop met Linux-containers nodig.
De geautomatiseerde PostgreSQL-tests gebruiken PGlite en vereisen geen Docker.

## Wat werkt

- Responsive homepage, voorbeeldmail, FAQ en privacy-informatie.
- Registratie, e-mailverificatie, opnieuw aanvragen, login/logout en herstel.
- Acht onboardingstappen met expliciete conceptopslag en bewaren bij Verder.
- Volledige lokale Nederlandstalige CPV 2008-basiswoordenlijst: 9.454 codes,
  45 divisies, uitklapbare hiërarchie, zoeken en paginering.
- CPV-selecties met expliciete keuze voor alleen de code of inclusief alle
  onderliggende codes; afzonderlijke CPV-opmerkingen.
- Eén lijst met gewenste keywords toevoegen, wijzigen en verwijderen.
- Bulkimport van publicatie-ID's/URL's van eerdere deelnames, deduplicatie,
  originele invoer en optionele toelichting. Historische voorbeelden worden niet opgehaald.
- Optionele bedragen zijn `null`, niet nul, als ze leeg worden gelaten.
- Dashboard met volledig profiel, bewerken, e-mailvoorkeuren, status en datums.
- Eigen gegevensdownload en database-export voor de beheerder.
- Verwijderverzoek via het dashboard, handmatig af te handelen.
- Optimistische revisiecontrole en transactionele opslag van alle lijsten.

Alleen bedrijfsnaam, bedrijfsomschrijving en ontvangstadres zijn nodig voor
afronding. Concepten mogen leeg zijn. Bewaar met **Tussentijds opslaan** of
**Bewaar en verder**; er is geen verborgen autosave of opslag van bedrijfsdata in
localStorage. Sessietokens worden door Supabase wel in browseropslag bewaard.
Een waarschuwing helpt bij het verlaten met niet-opgeslagen wijzigingen.

## Beheer en JSON-export

De CPV-selector gebruikt de officiële Nederlandse PIANOo-lijst (CPV 2008), met
9.454 basiscodes en 45 divisies. De bron-XLSX is meegeleverd; een importscript
genereert de lokale JSON en SQL-catalogus zonder extra Python-libraries. De
aanvullende woordenlijst is niet geïntegreerd. Zie [CPV-bron, herimport en
hiërarchie](docs/cpv.md). Voor offline verificatie van de generatie:

```powershell
uv run --no-project --python 3.11 scripts/import-cpv.py --check
```

De export is nu versie 3. Een exacte selectie exporteert één basiscode; een
selectie inclusief onderliggende codes exporteert alle betreffende basiscodes
expliciet, zodat de bestaande scanner ze exact kan matchen.

Er is bewust geen custom adminpaneel en geen service-role key op de website.
Gebruik Supabase Table Editor: companies → search_profiles → keywords/cpv_codes/
historical_tenders en subscriptions. De beheerder is een vertrouwde database-
beheerder; beperk wie je toegang tot het Supabase-project geeft.

Zoek bedrijf en status:

```sql
select c.id, c.company_name, c.contact_email, s.onboarding_completed,
       b.status, s.updated_at
from public.companies c
join public.search_profiles s on s.company_id=c.id
join public.subscriptions b on b.company_id=c.id
order by s.updated_at desc;
```

Kopieer de bedrijfs-UUID en exporteer in SQL Editor:

```sql
select jsonb_pretty(public.admin_export_config('BEDRIJFS-UUID'::uuid)) as configuration;
```

Kopieer de inhoud van de `configuration`-cel naar een UTF-8 `.json`-bestand.
Gebruik niet zonder controle de CSV-exportknop: die exporteert een CSV-wrapper,
geen zelfstandig JSON-document. De exportfunctie is niet uitvoerbaar voor
ingelogde gebruikers of anon. `docs/example-config.json` bevat uitsluitend fictie.
Zie [exportcontract](docs/export.md). De Python-scanner leest dit nog niet
automatisch: gebruik de gegevens om de scanner en workflow handmatig in te richten.

## Proefperiode handmatig activeren

`pending` → `submitted` wordt alleen bij bevestigde onboarding gezet. Andere
statuswijzigingen zijn voor de beheerder. Activeren met 14 dagen:

```sql
update public.subscriptions
set status='active', activated_at=now(), trial_started_at=now(),
    trial_ends_at=now()+interval '14 days'
where company_id='BEDRIJFS-UUID'::uuid;
```

Je kunt datums aanpassen in Table Editor. Voor stoppen:

```sql
update public.subscriptions set status='expired'
where company_id='BEDRIJFS-UUID'::uuid;
-- of status='disabled' om profielwijzigingen te blokkeren.
```

Er is geen automatische activering, verlopen-job, betaling of verlenging. Het
dashboard benoemt een verstreken einddatum ook als de beheerder de status nog
niet naar expired heeft gezet. Zelf aanvullen na indiening start de proef niet
opnieuw. Een disabled gebruiker kan eigen data lezen en verwijdering aanvragen.

Verwijderverzoeken bekijken:

```sql
select user_id, contact_email, deletion_requested_at from public.profiles
where deletion_requested_at is not null;
```

Handel het verzoek af via Authentication → Users → Delete user. Foreign keys
verwijderen het gekoppelde bedrijfsprofiel en de lijsten mee. Verwijder ook
eventuele handmatige exports/scannerconfiguraties buiten deze app. De app
registreert alleen het verzoek en belooft geen onmiddellijke verwijdering.

## Kwaliteitscontroles

```powershell
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm preview
pnpm exec playwright install chromium
pnpm test:e2e
```

Op Windows gebruikt de browserconfig de geïnstalleerde Chrome. Op Linux gebruikt
de browserconfig Playwright Chromium. Vitest test validatie, ID-normalisatie,
export, migraties en PostgreSQL-RLS met twee verschillende gebruikers. De
browsertests onderscheppen Supabase-aanroepen met expliciete fixtures: ze testen
interacties, **niet** de echte Supabase-mailaflevering. De databasebeveiliging
wordt daarnaast onafhankelijk in PostgreSQL getest. Zie `docs/verification.md`
voor de werkelijk uitgevoerde controles en de nog vereiste live acceptatietest.

## Gratis Cloudflare Pages-deployment (zelf uitvoeren)

De app is een echte Next.js App Router static export, geen SSR-site. Auth en
datamutaties gaan rechtstreeks naar Supabase met RLS/RPC-autorisatie. Daardoor
is geen OpenNext/Workers-runtime nodig.

1. Zet alleen dit project in je nieuwe GitHub-repository of kies in Cloudflare
   Pages de projectroot `tender-scanner-web` als je een monorepo houdt.
2. Cloudflare → Workers & Pages → Create → Pages → Git-repository verbinden.
3. Buildcommand: `pnpm install --frozen-lockfile && pnpm build`.
   Outputdirectory: `out`. Node-versie: 22 of nieuwer. Package manager: pnpm
   (volg de vastgelegde `packageManager` in package.json).
4. Voeg de drie publieke environmentvariables uit `.env.example` toe voor de
   build. Ze worden in de statische browserbundle ingebouwd. Gebruik geen
   secret- of service-role sleutel. Een env-wijziging vereist een nieuwe build.
5. Controleer de publieke privacytekst, contactgegevens, grondslag, bewaartermijn
   en verwerkersafspraken vóór echte aanmeldingen. Voeg indien nodig juridische
   bedrijfsgegevens toe; er zijn bewust geen verzonnen gegevens ingevuld.
6. Deploy pas als je dat zelf wilt. Voeg het uiteindelijke HTTPS-domein toe bij
   Supabase Site URL en de expliciete callback-URL's. Controleer SMTP.
7. Test de volledige aanmelding met twee aparte gebruikers en twee browsers.
   Controleer ook de securityheaders uit `public/_headers` op de echte host.

Cloudflare Free: 500 builds/maand, 20.000 bestanden en 25 MiB per bestand op het
moment van onderzoek. Supabase Free: 500 MB database, 50.000 MAU, 5 GB egress,
maximaal twee actieve gratis projecten; inactieve projecten kunnen na een week
pauzeren. Voor deze 5–20 persoons-PoC is dat naar verwachting voldoende, geen
garantie voor toekomstige limieten. Eigen domein/SMTP kunnen eigen kosten hebben;
deze zijn niet aangemaakt. [Actuele bronnen en keuzes](docs/architecture.md).

## Problemen oplossen

- **Accountomgeving niet aangesloten**: controleer `.env.local`, public key en
  project-URL; herstart dev of rebuild Cloudflare.
- **Registreren maar geen mail**: SMTP, toegestane adressen, rate limits en spam
  controleren. Supabase Logs → Auth toont providerproblemen; log geen tokens.
- **Link ongeldig/verlopen**: gebruik dezelfde browser, een nieuwe link en de
  exacte toegestane redirect-URL. Start niet meerdere herstelstromen tegelijk.
- **Profiel laden mislukt**: verifieer e-mail en voer migratie uit vóór registratie.
  Controleer bij een oud testaccount of de registratie-trigger rijen heeft gemaakt.
- **Profiel elders gewijzigd**: herlaad. De database weigert bewust verouderde
  writes zodat een ander tabblad niet wordt overschreven.
- **Opslaan mislukt**: controleer CPV-formaat, dubbele codes/keywords, e-mailadres
  en min/max-bedragen. De transactie rolt bij een fout volledig terug.
- **Uitgeschakeld**: de beheerder moet de status wijzigen; gebruikers kunnen dit
  niet omzeilen door een andere ID in een API-verzoek te zetten.
- **Build faalt onder een beperkte Windows-sandbox**: voer lokaal `pnpm build`
  uit in een normale terminal. Bij een lokale Turbopack-bug is
  `pnpm exec next build --webpack` een alternatief.

## Bewust buiten scope

Geen scannerintegratie, GitHub Actions-generatie, AI, documentdownloads,
historie-analyse, betalingen, automatische rapportmails, adminwebapp of meerdere
medewerkers per bedrijf. De huidige scannerrepository en workflows zijn niet
aangepast door deze PoC. Er is niets gepubliceerd en geen externe resource gemaakt.
