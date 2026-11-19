# Volledige CPV 2008-selector

## Bron en volledigheid

De primaire bron is het [Nederlandse CPV-werkboek van PIANOo](https://www.pianoo.nl/sites/default/files/media/documents/2022-07/overzicht_cpv_codes_simap.xlsx),
gekoppeld vanaf [PIANOo CPV-codes](https://www.pianoo.nl/nl/regelgeving/cpv-codes).
[TED](https://ted.europa.eu/nl/simap/cpv) bevestigt CPV 2008 als actuele
classificatie en beschrijft de hiërarchie. De TED-gids noemt 9.454 basiscodes.
Het geïmporteerde werkblad bevat precies die 9.454 unieke codes met Nederlandse
omschrijvingen, verdeeld over 45 divisies. Geen vertalingen of ontbrekende codes
zijn verzonnen. Code 72300000-8 heet in de bron bijvoorbeeld “Uitwerken van gegevens”;
de oude handmatige voorbeeldomschrijving is niet als officiële tekst gebruikt.

Scoutee is bekeken als technische referentie, maar er worden geen gegevens,
code of assets van Scoutee hergebruikt. De officiële PIANOo-bron volstaat. Zie
ook [TED's hergebruikbeleid](https://ted.europa.eu/nl/legal-notice) en Verordening
(EG) 213/2008. Bronvermelding en de verwerking zijn vastgelegd; er worden geen
TED-logo's of claims van officiële goedkeuring gebruikt.

Het tweede werkblad bevat 903 aanvullende codes. Dit is een aparte alfanumerieke
woordenlijst voor bijvoorbeeld materiaal of gebruik, geen extra niveau van de
numerieke basiswoordenlijst. Deze is geteld maar bewust niet in de selector,
whitelist of catalogustabel opgenomen.

## Bronbestanden en reproduceerbaarheid

- `data/cpv/source/pianoo_cpv.xlsx`: ongewijzigd bronwerkboek, 299.971 bytes.
- SHA-256: `307d7f4fe6ac5b19e8a558ed8d9bc4f4591b96b7a09fb79b23d2ecb39d4a8608`.
- `scripts/import-cpv.py`: leest XLSX rechtstreeks met Python-standaardbibliotheek.
  Er is geen Excel, pandas, openpyxl of webbackend nodig.
- `src/data/cpv-2008-nl.json`: gegenereerde lokale dataset met metadata.
- `supabase/migrations/202611190002_cpv_catalog.sql`: gegenereerde catalogus/seed.

Vanuit de projectmap, met Python 3.11+ of uv:

```powershell
# Offline opnieuw genereren uit het meegeleverde officiële bronbestand:
uv run --no-project --python 3.11 scripts/import-cpv.py
# Alleen controleren of bron en gegenereerde bestanden overeenkomen:
uv run --no-project --python 3.11 scripts/import-cpv.py --check
# Optioneel de bron opnieuw ophalen vóór generatie:
uv run --no-project --python 3.11 scripts/import-cpv.py --download
```

Met een gewone Python-installatie kan `python scripts/import-cpv.py` ook.
Python/uv is uitsluitend nodig voor herimport, niet voor de website. De import
stopt bij verkeerde formaten, ontbrekende omschrijvingen, dubbele codes of een
ander aantal dan 9.454. De uitvoer is deterministisch en bevat geen wisselende
generatietijd. Bij een wijziging van de officiële bron moet een **nieuwe**
databasemigratie worden gemaakt; overschrijf of herhaal geen al toegepaste
migraties op een bestaande database.

## Structuur en zoeken

Alle codes zijn strings. Iedere entry bevat `code`, `base_code`, `description_nl`,
`level`, `precision` en `parent_code`. Vooraanstaande nullen blijven behouden.
`precision` is het aantal relevante codeposities, met minimaal twee posities:
2 divisie, 3 groep, 4 klasse, 5 categorie, 6–8 subcategorie. De ouder is de
naastgelegen minder specifieke **bestaande** code door rechts te veralgemenen met
nullen. Ontbrekende tussenniveaus worden niet verzonnen.

Voorbeeld: `34114200-1` (Politieauto's) valt onder `34114000-9` (Speciale voertuigen).
De boom is gecontroleerd op bestaande ouders, cycli en volledige bereikbaarheid
van alle 9.454 codes vanuit de 45 divisies.

Een vooraf opgebouwde, accent-/hoofdletterongevoelige clientindex zoekt op code
en Nederlandse omschrijving. Meerdere zoekwoorden moeten allemaal voorkomen.
De DOM rendert maximaal 50 resultaten per pagina. Zonder zoekopdracht tonen we
divisies met uitklapbare groepen/klassen/categorieën/subcategorieën; niet meteen
duizenden verborgen DOM-elementen. De lokale dataset is circa 1,45 MB ongecomprimeerd.
Er is geen externe CPV-API en er komen geen runtimekosten voor de classificatie bij.

## Selectie en opslag

Een vinkje selecteert exact één code. “Inclusief onderliggende codes kiezen” of
de expliciete bereikkeuze op de geselecteerde kaart zet `include_descendants=true`.
Een code openen kiest niets. Een gedekte subcode is herkenbaar maar wordt niet
stiekem als een tweede expliciete selectie aangevinkt.

Per profiel blijven `public.cpv_codes`-rijen bestaan met:

- `cpv_code`: canonieke volledige code met het officiële controlecijfer.
- `description`: officiële Nederlandse omschrijving.
- `include_descendants`: expliciete boolean, standaard false.
- `original_description`: eerdere eigen omschrijving, indien aanwezig.

Er zijn maximaal 150 expliciete hoofdselecties; het aantal geëxporteerde subcodes
kan groter zijn. Exact en subtree voor dezelfde basiscode zijn één selectie met
een bewerkbaar bereik. Overlappende selecties zijn toegestaan en worden in de
export gededupliceerd. Handmatig vrije codes of officiële omschrijvingen wijzigen
is vervangen door selecteren uit de dataset. Eigen toelichting hoort bij CPV-opmerkingen.

De client valideert bestaan en controlecijfer via de dataset; PostgreSQL valideert
dit opnieuw via de catalogus, trigger en foreign key. Een fout controlecijfer
wordt niet stilzwijgend gerepareerd. Authenticated kan de catalogus alleen lezen;
anon heeft geen databasecatalogustoegang. De statische classificatiedata zelf
zijn uiteraard publiek. Gebruikersselecties blijven onder de bestaande RLS en
ownership-gecontroleerde save-RPC vallen. Oude interne v1-functies zijn niet
aanroepbaar door gewone gebruikers.

## Bestaande Supabase-database bijwerken

Als `202611190001_initial.sql` al is toegepast, voer **alleen deze twee nieuwe
bestanden, in deze volgorde**, in de Supabase SQL Editor uit:

1. `202611190002_cpv_catalog.sql`
2. `202611190003_cpv_selection.sql`

Beide bestanden zijn transactioneel. Geen gebruikers of selecties worden gewist.
Bekende achtcijferige selecties krijgen hun officiële controlecijfer; het oude
gedrag blijft **exact** (`include_descendants=false`). Eerdere omschrijvingen
blijven bewaard in `original_description`. Eventuele onbekende oude codes blijven
staan, zichtbaar met een melding. Zij moeten expliciet worden vervangen of
verwijderd vóór nieuwe opslag/export. Een NOT VALID foreign key behoudt oude
onbekende rijen, maar accepteert geen nieuwe ongeldige selecties.

Een geteste oude schrijf-RPC wordt intern hergebruikt voor de overige profielvelden.
De nieuwe wrapper verzorgt CPV-validatie/bereik en retourneert opnieuw het volledige
profiel. De save-call controleert eerst de catalogusversie/hash. Zonder de nieuwe
migraties stopt opslaan met een duidelijke melding in plaats van subtree stil
als exact te bewaren. Bestaande profielen kunnen wel worden gelezen.

Nieuwe projecten voeren alle drie de migraties in volgorde uit vóór registratie.
De publieke publishable key kan deze migraties niet uitvoeren; gebruik SQL Editor
als beheerder. De migraties zijn lokaal echt getest, maar toepassing op de live
database vereist beheerderstoegang en is niet impliciet gedaan door codewijzigingen.

## Export en de bestaande scanner

Exportversie 2 bevat dezelfde hoofdstructuur, met toegevoegde CPV-semantiek:

```json
{
  "schema_version": 2,
  "scanner_config": {
    "cpv_whitelist": ["72000000"],
    "cpv_details": [{
      "code": "72000000-5",
      "description": "IT-diensten: adviezen, softwareontwikkeling, internet en ondersteuning",
      "include_descendants": false,
      "original_description": null
    }],
    "cpv_dataset": { "classification": "CPV 2008", "source_sha256": "307d7f4fe6ac5b19e8a558ed8d9bc4f4591b96b7a09fb79b23d2ecb39d4a8608" }
  }
}
```

De Python-scanner gebruikt een **exacte set-overlap**, geen prefixfilter. Daarom
bevat `cpv_whitelist` bij `include_descendants=true` de geselecteerde basiscode én
alle bestaande onderliggende basiscodes. De array is gesorteerd en uniek, ook
bij overlappende selecties. Er worden geen codes gegenereerd door getallen op
te hogen. Bij `include_descendants=false` wordt alleen de expliciet
geselecteerde code opgenomen. “Geen prefixfilter” betekent ook dat een match op
een bovenliggende code niet automatisch de omgekeerde richting op werkt.

Zowel `admin_export_config` in SQL als de eigen gegevensdownload gebruiken deze
uitwerking. Tests vergelijken beide exports exact. Gebruik de uitgebreide
whitelist later handmatig als `CPV_WHITELIST_RAW` in een klantspecifieke scanner.
De Python-scanner is niet gewijzigd. De selectie/prompt/workflow wordt nog steeds
handmatig ingericht; versie 2 is geen automatische scannerintegratie.
