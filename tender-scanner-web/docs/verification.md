# Verificatie en resterende live inrichting

## Uitgevoerd op 19 november 2026

- Dependency-installatie met pnpm; reproduceerbare `pnpm-lock.yaml` aanwezig.
- TypeScript `tsc --noEmit`: geslaagd.
- ESLint: geslaagd zonder fouten of waarschuwingen.
- Vitest: **30 tests geslaagd**, verdeeld over profiel/ID/exportvalidatie,
  buildconfiguratie, volledige CPV-data, hiërarchie/zoeken/selectie en database-integratie.
- PostgreSQL-migratie echt uitgevoerd op PGlite (lokale PostgreSQL/WASM-engine),
  met gemodelleerde Supabase-rollen en `auth.uid()`-context. Gebruiker A/B
  hebben verschillende UUID's. Getest: eigen rijen lezen, andermans rijen niet
  lezen, directe writes weigeren, beheerexport weigeren, ongeverifieerde toegang
  weigeren, transactioneel opslaan, revisieconflict, lijsten bewerken/verwijderen,
  afronden → submitted zonder proefstart, adminactivering, disabled-mutaties en
  verzoek tot verwijdering. SQL- en TypeScript-export zijn exact vergeleken.
- Playwright met echte lokale Chrome: vijf browserflows geslaagd voor de publieke
  pagina's, desktop/mobiel, accountinteracties en volledige onboarding met latere
  wijziging. Supabase-verkeer wordt daarbij met benoemde fixtures onderschept.
  Registratie, login, logout en herstelmail-aanvraag zijn gecontroleerd, evenals
  CPV-boomnavigatie, exacte/subtree-selecties, opslaan/herladen en mobiel gebruik.
- Het importscript is opnieuw uitgevoerd met `--check`: de lokale PIANOo-XLSX,
  bronhash, 9.454 Nederlandse codes en gegenereerde JSON/SQL komen overeen.
- De twee CPV-migraties zijn ook op een bestaande testdatabase met legacyselecties
  uitgevoerd: bekende basiscodes zijn canoniek, eigen omschrijvingen blijven
  bewaard en onbekende oude rijen zijn niet verwijderd. Nieuwe onbekende codes
  en foutieve controlecijfers worden geweigerd. SQL- en TypeScript-subtree-exports
  zijn identiek. Gewone gebruikers kunnen de catalogus niet wijzigen.
- Homepage screenshots op 1280px en 390px bekeken; geen horizontale overflow op
  de geteste mobiele breedte. Reviewstap als screenshot vastgelegd.
- Next.js productiebuild: geslaagd, elf statische pagina-uitvoeritems. `out/`
  bevat HTML, assets en Cloudflare `_headers`. Geen server-runtime benodigd.

De eerste sandboxbuild kon een Turbopack-hulpproces niet verbinden. Dezelfde
productiebuild buiten die sandbox slaagde. De eerste browserchecks vonden
onnauwkeurige labels/selectors; de labels zijn toegankelijk gekoppeld en de
gecorrigeerde flows zijn opnieuw uitgevoerd. Er worden geen mislukte controles
als geslaagd aangemerkt.

## Nog niet uitgevoerd / niet geclaimd

De website is lokaal verbonden met het
Supabase-project via `.env.local` (uitgesloten van Git). De live, alleen-lezen
verbindingscontrole is geslaagd: publieke sleutel geaccepteerd, e-mailregistratie
ingeschakeld, e-mailbevestiging vereist, de acht tabellen (inclusief cpv_catalog)
en get_workspace, save_onboarding, admin_export_config en get_cpv_catalog_info
weigeren anonieme toegang met code 42501. De eigenaar heeft bevestigd dat alle
drie de migraties zijn geslaagd en heeft inmiddels een websiteaccount aangemaakt
en een profiel ingevuld. Dat is gebruikersevidence voor die stappen; opslag na
opnieuw inloggen en definitieve indiening zijn nog niet afzonderlijk bevestigd.

- Het Supabase-project is door de eigenaar aangemaakt. De verbinding en anonieme
  PostgREST-toegangsweigeringen zijn inmiddels live getest; SMTP en ingelogde
  API-isolatie met twee echte accounts zijn nog niet afzonderlijk getest.
- Registratie is door de eigenaar doorlopen. Ontvangst van verificatie- en
  herstelmails en de SMTP-configuratie zijn nog niet afzonderlijk bevestigd.
  Browsertests controleren de clientflow met fixtures.
- Geen Cloudflare- of GitHub-websiteproject aangemaakt en geen deployment.
- Geen commerciële privacytekst, bewaartermijn of verwerkersafspraken vastgesteld.
- De eerste oplevering had een voorbeeldlijst; deze is inmiddels vervangen door
  alle 9.454 officiële Nederlandse CPV-basiscodes. De nieuwe CPV-migraties zijn
  lokaal getest en volgens de eigenaar succesvol op de live database toegepast.
- Geen scannerintegratie, betalingen, AI of automatische rapportage.

De PoC-broncode en lokale checks zijn opgeleverd. Live acceptatiecriteria voor
externe registratie, mailverificatie en opslag op het gekozen Supabase-project
zijn pas te bevestigen na onderstaande inrichting en handmatige test.

## Live acceptatietest na de dashboardinrichting

1. Voer de migratie uit, configureer de publieke URL/key, SMTP, e-mailbevestiging
   en de exacte callback-URL's volgens de README.
2. Registreer gebruiker A met een echt toegankelijk testadres. Controleer dat
   inloggen vóór verificatie wordt geweigerd. Open de verificatiemail in dezelfde
   browser en controleer het dashboard.
3. Vul alle acht stappen in, bewaar halverwege, log uit en opnieuw in. Controleer
   dat data terugkomt. Dien in: status submitted, proefdatums nog null.
4. Maak gebruiker B in een andere browser aan. Vul bewust andere gegevens in.
   Controleer in de browser en met diens Supabase-JWT rechtstreeks via REST dat
   filteren op de bedrijfs-ID van A geen rijen teruggeeft. Wijzigen moet worden
   geweigerd. Controleer hetzelfde voor CPV, keywords, historie en abonnement.
5. Probeer met B via RPC een owner-ID, bedrijfs-ID of status te injecteren. Dit
   mag nooit A aanpassen of B activeren. `admin_export_config` en
   `workspace_for_company` mogen niet uitvoerbaar zijn met A/B/anon.
6. Exporteer A als beheerder via SQL Editor. Valideer dat het resultaat gewone
   JSON met schema_version 2 is en dat B's gegevens er niet in staan.
7. Activeer A met begin/einddatum. Controleer de dashboardstatus. Bewerk A's
   zoekprofiel: de proefdatums mogen niet opnieuw starten. Zet A op disabled en
   controleer dat writes worden geweigerd.
8. Test wachtwoord vergeten → echte mail → link → nieuw wachtwoord → logout/login.
   Test ook een verlopen link en de opnieuw-aanvragenknop.
9. Vraag verwijdering aan en controleer `profiles.deletion_requested_at`.
   Verwijder daarna de testuser via Auth en controleer cascadeverwijdering.
10. Controleer de echte HTTPS-site op desktop/mobiel en securityheaders. Nodig
    pas daarna de eerste 5–20 testers uit.

`tests/database.test.ts` is de herhaalbare lokale beveiligingstest. De bovenstaande
stappen toetsen aanvullend de echte projectinstellingen, JWT-uitgifte, API-laag
en e-mailprovider; die kunnen niet door alleen frontendmocks worden bewezen.
