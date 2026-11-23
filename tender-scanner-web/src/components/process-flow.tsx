const steps = [
  { title: "Jij vult je bedrijfsprofiel in", body: "Beschrijf je diensten, kies je CPV-codes en voeg gewenste zoektermen en opdrachten waaraan je hebt deelgenomen toe." },
  { title: "Wij richten de scanner handmatig in", body: "We gebruiken je profiel voor de inrichting en activeren daarna je scanner. Alleen aanmelden start nog geen scans. Je proefperiode begint bij activering." },
  { title: "De scanner haalt recente TenderNed-publicaties op", body: "Binnen het ingestelde tijdvak worden openbare publicaties opgehaald. De selectie hangt af van de informatie en documenten die TenderNed beschikbaar stelt." },
  { title: "Eerst controleren we de CPV-codes", body: "Alleen aanbestedingen met minstens één CPV-code binnen jouw selectie gaan verder. Geen overeenkomst of geen beschikbare CPV-code? Dan wordt de aanbesteding overgeslagen, vóór de inhoudelijke analyse.", outcome: "Afgevallen op CPV? Zoektermen of AI kunnen deze aanbesteding daarna niet alsnog meenemen." },
  { title: "Daarna zoeken we je keywords in documenten", body: "De scanner leest ondersteunde PDF- en DOCX-bestanden, ook uit ZIP-bestanden. Zonder een gevonden zoekterm gaat de aanbesteding niet door naar de leidraad-analyse. Ontbrekende of onleesbare documenten kunnen de beoordeling beperken." },
  { title: "We zoeken een leidraad en beoordelen die met AI", body: "Na een zoektermhit kiest de scanner een leidraad op basis van de documentnaam. Als die niet wordt gevonden, wordt de AI-analyse overgeslagen. Als de analyse lukt, volgt een GO-, MAYBE- of NO_GO-beoordeling." },
  { title: "Je ontvangt de GO-selectie per e-mail", body: "De rapportage bevat een overzichtelijke samenvatting van de positief beoordeelde opdrachten en aandachtspunten. Overgeslagen documenten en redenen worden in een apart scanoverzicht vastgelegd. Je beoordeelt zelf de officiële stukken en beslist of je inschrijft." },
];

export function ProcessFlow() {
  return <div className="process-flow">
    <h3>Van jouw profiel naar een aanbestedingsselectie</h3>
    <p>Dit zijn de stappen na inrichting en activering. Bij iedere filter kunnen aanbestedingen afvallen; de scanner geeft daardoor geen garantie dat iedere interessante opdracht wordt gevonden.</p>
    <ol className="process-steps">{steps.map(step => <li key={step.title}>
      <h4>{step.title}</h4><p>{step.body}</p>
      {step.outcome && <p className="process-outcome"><strong>{step.outcome}</strong></p>}
    </li>)}</ol>
    <aside className="notice cpv-guidance" aria-label="Een complete CPV-selectie is belangrijk">
      <strong>Neem de tijd voor een complete CPV-selectie</strong>
      <p>Een passende aanbesteding kan onder een andere code gepubliceerd worden dan je verwacht. Kies daarom bij twijfel liever meer mogelijk relevante codes dan te weinig. Gebruik waar passend ‘Inclusief onderliggende codes kiezen’. Alleen een categorie openklappen selecteert nog niets.</p>
      <p>Een ruimere keuze kan meer resultaten opleveren die minder goed passen. Een ontbrekende code kan betekenen dat een interessante opdracht helemaal niet door de eerste filter komt.</p>
    </aside>
  </div>;
}
