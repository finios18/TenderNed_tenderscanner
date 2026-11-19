# Architectuur en beslissingen

## Relevante bestaande scanner

De Python-scanner combineert TenderNed-publicatiefilters, een CPV-whitelist,
inhoudelijke keywords en titelherkenning van PDF/DOCX-leidraden. Optioneel
beoordeelt OpenAI een leidraad. Resultaten worden GO/MAYBE/NO_GO met
JSON-output; GitHub Actions maakt een leesbare HTML-mail. Voor de website zijn
vooral bedrijfscontext, CPV-whitelist, keywords en mailfrequentie relevant.
Negatieve keywords, historie en diverse voorkeuren uit deze website hebben
nog geen automatische implementatie in de scanner. De export is input voor
handmatige inrichting, geen claim van directe plug-and-play compatibiliteit.

## Eenvoudige architectuur

Next.js App Router + React + TypeScript + Tailwind, geëxporteerd als statische
HTML/CSS/JS. De eigen componenten gebruiken Lucide-iconen; geen grote
formulier-/componentframeworks. Inter en andere remote fonts zijn bewust niet
nodig: systeemfonts vermijden een externe build-/trackingafhankelijkheid.

Supabase JS beheert authsessies. PKCE-verificatie en herstel lopen via één
callbackpagina. Er zijn geen server routes, server actions of privédata in de
statische build. Client-side routes controleren de ingelogde gebruiker voor UX;
de echte toegangsgrens is PostgreSQL RLS en de expliciete ownershipchecks in
RPC's. Browseropslag voor sessietokens is een bewuste SPA-afweging; er zijn geen
HttpOnly serversessies. Geen onbeveiligde HTML-injectie of externe scripts.

RLS is aan op alle zeven gebruikerstabellen en op de CPV-catalogus. Authenticated
mag alleen eigen gebruikersrijen en de gedeelde, alleen-lezen catalogus lezen.
Schrijven gebeurt via `save_onboarding`, een SECURITY DEFINER-functie
met lege search_path, auth.uid-controle, verificatiecheck en server-side validatie.
De functie accepteert geen gebruiker-/bedrijf-ID: ze bepaalt het bedrijf op basis
van de identiteit uit de door Supabase geverifieerde JWT. Eigendom, status en
trialdata komen nooit uit de invoer. Directe REST-writes worden door grants en RLS
geweigerd. De complete payload wordt transactioneel vervangen en revisiegewijs
bijgewerkt. Dit past bij een PoC met één eigenaar en voorkomt half opgeslagen lijsten.

`owner_user_id` is uniek: één gebruiker, één bedrijf. Bij uitbreiding kan een
company_members-tabel ownership vervangen in autorisatie. De huidige foreign keys
en company_id-koppelingen hoeven daarvoor niet te worden weggegooid.

Adminbeheer blijft in Supabase, inclusief een afgeschermde exportfunctie.
Geen service-role key op de website. Activering en eindstatus blijven handmatig.
Registratie maakt lege profielrijen; de proefperiode begint niet bij registratie.

## Dataset en validatie

`src/lib/cpv.ts` gebruikt de volledige lokale PIANOo/TED CPV 2008-dataset:
9.454 Nederlandse basiscodes en 45 divisies. Een reproduceerbare standaard-Python
import levert JSON en een SQL-catalogus. Codes worden zowel client-side als in
PostgreSQL op bestaan en controlecijfer gevalideerd. De selectie bewaart expliciet
of onderliggende codes meetellen; de export breidt die zo nodig uit voor de exacte
matching van de bestaande scanner. Zie [bron, import, migraties en semantiek](cpv.md).

Historische ID's worden alleen uit positieve cijfers of de herkenbare HTTPS-route
`tenderned.nl/aankondigingen/overzicht/ID[/publicatie]` gehaald. Andere hosts en
onbekende paden worden geweigerd, niet geraden. ID's kunnen in meerdere
categorieën staan; binnen één categorie is de ID uniek. Geen TenderNed-netwerkcalls.

## Gratis hosting: gecontroleerd op 19 november 2026

- [Next.js static export](https://nextjs.org/docs/app/guides/static-exports):
  geschikt voor een client-app met externe auth/data; SSR-features zijn niet nodig.
- [Cloudflare Pages Next.js static](https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/):
  output `out`; geen adapter/Worker nodig. Een dynamische Next.js-app zou een
  ander deploymentpad hebben, daarom is deze eenvoudige export gekozen.
- [Cloudflare Pages-limieten](https://developers.cloudflare.com/pages/platform/limits/):
  Free 500 builds/maand, 20.000 bestanden en maximaal 25 MiB per bestand.
- [Supabase Free](https://supabase.com/pricing): 500 MB database, 50.000 MAU,
  5 GB egress en pauzeren na een week inactiviteit. Gratis projecten zijn niet
  bedoeld als gegarandeerd altijd beschikbare productie-infrastructuur.
- [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp): ingebouwde
  mail is beperkt tot geautoriseerde teamadressen; eigen SMTP is nodig voor
  externe testers. Leveringslimieten en eventuele domeinkosten apart controleren.
- [PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow): een link
  moet in dezelfde browser worden geopend omdat daar de verifier aanwezig is.

Er is geen betaalde fallback gekozen. Een Cloudflare-account, Supabase-project,
SMTP-configuratie en eventueel domein moeten nog door de eigenaar worden ingericht.

## Privacygrenzen

De publieke privacytekst benoemt welke gegevens en sessieopslag er zijn. De
beheerder moet vóór livegebruik de bedrijfsidentiteit, grondslag, bewaartermijn en
verwerkersafspraken invullen. De app heeft een echt opgeslagen verwijderverzoek,
geen verzonnen automatische verwijdering. Exportbestanden buiten de database
blijven een verantwoordelijkheid van de beheerder.
