# Exportcontract v2

`schema_version: 2` is het gedocumenteerde JSON-contract, gegenereerd door
`public.admin_export_config(company_uuid)` in PostgreSQL en door
`src/lib/export/config.ts` voor de eigen gegevensdownload. Een integratietest
vergelijkt beide structuren exact. Alle vrije tekst is gebruikersinput; behandel
die bij toekomstig promptgebruik als data, nooit als systeeminstructies.

- `customer_id`: stabiele bedrijfs-UUID.
- `company`: alle bedrijfsvelden plus `name` en `description` voor scannercontext.
- `contact`: ontvangstadres en contactpersoon.
- `business_context`: volledige context voor latere handmatige promptinrichting.
- `scanner_config`: actieve CPV-basiscodes, originele codes/omschrijvingen,
  CPV-opmerkingen, positieve `keywords`, aparte `negative_keywords`, numerieke
  `email_frequency_days` (1/2/3/7/14), mailvoorkeuren, regio, nullable min/max,
  opdrachtsoorten, kopers, certificeringen en aanvullende wensen.
  `cpv_details` bevat volledige officiële codes en `include_descendants` per
  selectie. `cpv_dataset` vermeldt classificatie en bronhash. `cpv_whitelist`
  bevat alle unieke gesorteerde achtcijferige codes die daadwerkelijk moeten
  matchen; subcodes worden uitsluitend uitgewerkt bij `include_descendants=true`.
- `historical_tenders`: drie arrays `participated`, `interesting` en
  `not_interesting`, met `publication_id`, `original_input` en `notes`.
- `subscription`: handmatige status, begin/einddatum en activeringsmoment (of null).
- `onboarding_completed` en `updated_at`: volledigheid en laatste wijziging.

Lege bedragen/datums zijn null; lege tekst is een lege string; lege lijsten zijn
lege arrays. Bedragen zijn EUR. Status of confidence van een echte aanbesteding
wordt niet door deze website berekend. Historische publicaties worden niet
verrijkt. Er worden geen inlogtokens, wachtwoorden of sleutels geëxporteerd.

De eigenaar gebruikt deze export handmatig voor de bestaande scanner. Er is geen
automatische import, promptgeneratie, workflowgeneratie of rapportverzending.

Versie 2 vervangt de eerdere CPV-voorbeeldinvoer en maakt bereik expliciet.
De overige hoofdvelden blijven beschikbaar. Bestaande selecties worden als
exact behouden. Zie [CPV-documentatie](cpv.md) voor migratie en legacywaarden.
