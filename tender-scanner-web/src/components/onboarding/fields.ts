export const stepLabels = ["Je bedrijf", "Expertise & diensten", "CPV-codes", "Zoektermen", "Eerdere opdrachten", "Voorkeuren", "Je e-mail", "Controleren"];
export const businessFields = [
  ["business_description", "Wat doet jouw bedrijf?", "Bijvoorbeeld: wij detacheren data-specialisten bij gemeenten en uitvoeringsorganisaties."],
  ["services_description", "Welke producten of diensten bied je aan?", "Beschrijf wat je levert: personele inzet, advies, een product of een compleet resultaat."],
  ["sectors", "In welke sectoren ben je actief?", "Bijvoorbeeld: overheid, zorg, onderwijs, financiële dienstverlening."],
  ["desired_contracts", "Welke soorten opdrachten zoek je?", "Bijvoorbeeld: raamovereenkomsten voor tijdelijke inhuur of adviesopdrachten."],
] as const;
export const preferenceFields = [
  ["preferred_contract_types", "Interessante soorten opdrachten", "Bijvoorbeeld: inhuur, raamovereenkomst, DAS, advies of projecten."],
  ["additional_requirements", "Aanvullende wensen en uitsluitingen", "Alles wat verder belangrijk is bij het beoordelen van een opdracht."],
] as const;
export const companyLabels = { company_name: "Bedrijfsnaam", website: "Website", kvk_number: "KvK-nummer", contact_person: "Contactpersoon", contact_email: "Contact-e-mailadres", phone_number: "Telefoonnummer", city: "Vestigingsplaats", company_size: "Bedrijfsgrootte" };
