# Exportcontract v3

`schema_version: 3` is het gedocumenteerde JSON-contract, gegenereerd door
`public.admin_export_config(company_uuid)` in PostgreSQL en door
`src/lib/export/config.ts` voor de eigen gegevensdownload. Een integratietest
vergelijkt beide structuren exact. Alle vrije tekst is gebruikersinput; behandel
die bij toekomstig promptgebruik als data, nooit als systeeminstructies.

- `customer_id`: stabiele bedrijfs-UUID.
- `company`: alle bedrijfsvelden plus `name` en `description` voor scannercontext.
- `contact`: ontvangstadres en contactpersoon.
- `business_context`: volledige context voor latere handmatige promptinrichting.
- `scanner_config`: actieve CPV-basiscodes, originele codes/omschrijvingen,
  CPV-opmerkingen, gewenste `keywords`, numerieke
  `email_frequency_days` (1/2/3/7/14), mailvoorkeuren, nullable min/max,
  opdrachtsoorten en aanvullende wensen.
  `cpv_details` bevat volledige officiële codes en `include_descendants` per
  selectie. `cpv_dataset` vermeldt classificatie en bronhash. `cpv_whitelist`
  bevat alle unieke gesorteerde achtcijferige codes die daadwerkelijk moeten
  matchen; subcodes worden uitsluitend uitgewerkt bij `include_descendants=true`.
- `historical_tenders`: één array met uitsluitend opdrachten waaraan is deelgenomen,
  met `publication_id`, `original_input` en `notes`.
- `subscription`: handmatige status, begin/einddatum en activeringsmoment (of null).
- `onboarding_completed` en `updated_at`: volledigheid en laatste wijziging.

Lege bedragen/datums zijn null; lege tekst is een lege string; lege lijsten zijn
lege arrays. Bedragen zijn EUR. Status of confidence van een echte aanbesteding
wordt niet door deze website berekend. Historische publicaties worden niet
verrijkt. Er worden geen inlogtokens, wachtwoorden of sleutels geëxporteerd.

De eigenaar gebruikt deze export handmatig voor de bestaande scanner. Er is geen
automatische import, promptgeneratie, workflowgeneratie of rapportverzending.

Versie 3 verwijdert specialisaties, uitgesloten diensten, onderscheidend vermogen,
regio, voorkeursopdrachtgevers en certificeringen. Keywords hebben geen type
meer en eerdere opdrachten geen categorie. De CPV-werking uit versie 2 blijft
behouden. Migreer met `202611230001_simplify_profile.sql`; negatieve keywords en
niet-deelgenomen voorbeelden worden bewust verwijderd. Oudere exports blijven
bestanden volgens hun eigen schema en worden niet automatisch omgezet.
