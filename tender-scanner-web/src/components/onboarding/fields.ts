export const stepLabels = ["Je bedrijf", "Expertise & diensten", "CPV-codes", "Zoektermen", "Eerdere opdrachten", "Voorkeuren", "Je e-mail", "Controleren"];
export const businessFields = [
  ["business_description", "Wat doet jouw bedrijf?", "Bijvoorbeeld: wij detacheren data-specialisten bij gemeenten en uitvoeringsorganisaties."],
  ["services_description", "Welke producten of diensten bied je aan?", "Beschrijf wat je levert: personele inzet, advies, een product of een compleet resultaat."],
  ["specializations", "Wat zijn jullie belangrijkste specialisaties?", "Bijvoorbeeld: data engineering, BI, informatieanalyse, cloudmigraties."],
  ["sectors", "In welke sectoren ben je actief?", "Bijvoorbeeld: overheid, zorg, onderwijs, financiële dienstverlening."],
  ["desired_contracts", "Welke soorten opdrachten zoek je?", "Bijvoorbeeld: raamovereenkomsten voor tijdelijke inhuur of adviesopdrachten."],
  ["excluded_services", "Wat lever je nadrukkelijk niet?", "Bijvoorbeeld: geen hardware, licenties of 24/7-beheer."],
  ["competitive_advantages", "Wat onderscheidt jouw bedrijf?", "Denk aan ervaring, nichekennis, werkwijze en beschikbare professionals."],
] as const;
export const preferenceFields = [
  ["geographic_preferences", "Gewenste regio’s", "Bijvoorbeeld: heel Nederland, Randstad of specifiek Noord-Brabant."],
  ["preferred_contract_types", "Interessante soorten opdrachten", "Bijvoorbeeld: inhuur, raamovereenkomst, DAS, advies of projecten."],
  ["preferred_buyers", "Voorkeur voor opdrachtgevers", "Bijvoorbeeld: gemeenten, ministeries of bepaalde uitvoeringsorganisaties."],
  ["certifications", "Certificeringen en vereisten die je bezit", "Bijvoorbeeld: ISO 9001, ISO 27001, SNA of specifieke branche-erkenningen."],
  ["additional_requirements", "Aanvullende wensen en uitsluitingen", "Alles wat verder belangrijk is bij het beoordelen van een opdracht."],
] as const;
export const companyLabels = { company_name: "Bedrijfsnaam", website: "Website", kvk_number: "KvK-nummer", contact_person: "Contactpersoon", contact_email: "Contact-e-mailadres", phone_number: "Telefoonnummer", city: "Vestigingsplaats", company_size: "Bedrijfsgrootte" };
