import { Fragment } from "react";
import type { Profile } from "@/lib/validation/profile";
import { businessFields,companyLabels,preferenceFields,stepLabels } from "./fields";
import { historyLabels } from "./editors";
export function Review({ profile: p, edit }: { profile: Profile; edit: (step:number)=>void }) {
  const value=(v:unknown)=>v===null || v==="" ? "Niet ingevuld" : String(v);
  function rows(entries: [string,unknown][]) {return <dl>{entries.map(([label,v])=><Fragment key={label}><dt>{label}</dt><dd>{value(v)}</dd></Fragment>)}</dl>;}
  const sections = [
    rows(Object.entries(companyLabels).map(([key,label])=>[label,p.company[key as keyof Profile["company"]]])),
    rows(businessFields.map(([key,label])=>[label,p.search[key]])),
    <div key="cpv"><ul>{p.cpv_codes.map(c=><li key={c.code}>{c.code} · {c.description || "Geen omschrijving"} <strong>({c.include_descendants ? "inclusief onderliggende codes" : "alleen deze code"})</strong></li>)}</ul>{!p.cpv_codes.length && <p>Nog geen CPV-codes toegevoegd</p>}<p>Opmerkingen: {value(p.search.cpv_notes)}</p></div>,
    rows([["Positief",p.keywords.filter(k=>k.type==="positive").map(k=>k.keyword).join(", ")],["Negatief",p.keywords.filter(k=>k.type==="negative").map(k=>k.keyword).join(", ")]]),
    <div key="history">{Object.entries(historyLabels).map(([key,label])=><div key={key}><strong>{label}</strong><ul>{p.historical_tenders.filter(t=>t.category===key).map(t=><li key={t.publication_id}>{t.publication_id}{t.notes ? ` — ${t.notes}` : ""}</li>)}</ul>{!p.historical_tenders.some(t=>t.category===key) && <p>Geen voorbeelden opgegeven</p>}</div>)}</div>,
    rows([...preferenceFields.map(([key,label])=>[label,p.search[key]] as [string,unknown]),["Minimale waarde",p.search.minimum_contract_value===null?null:`€ ${p.search.minimum_contract_value.toLocaleString("nl-NL")}`],["Maximale waarde",p.search.maximum_contract_value===null?null:`€ ${p.search.maximum_contract_value.toLocaleString("nl-NL")}`]]),
    rows([["Frequentie",`Iedere ${p.search.email_frequency_days} dag${p.search.email_frequency_days===1?"":"en"}`],["Ontvangstadres",p.search.notification_email],["Opmerkingen",p.search.email_notes]]),
  ];
  return <>{sections.map((content,index)=><section className="review-section" key={index}><div className="review-heading"><h3>{stepLabels[index]}</h3><button type="button" className="text-link" style={{background:"none",border:0}} onClick={()=>edit(index)}>Wijzigen<span className="sr-only">: {stepLabels[index]}</span></button></div>{content}</section>)}</>;
}
