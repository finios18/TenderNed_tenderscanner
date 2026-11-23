"use client";
import { cloneElement, isValidElement, useId, useState, type ReactElement, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";
import { type Profile } from "@/lib/validation/profile";
import { parsePublications } from "@/lib/validation/tenders";

export function Field({ label, hint, children, optional=false, wide=false }: { label: string; hint?: string; children: ReactNode; optional?: boolean; wide?: boolean }) {
  const id=useId();
  const control=isValidElement(children)?cloneElement(children as ReactElement<{id?:string;"aria-describedby"?:string}>,{id,"aria-describedby":hint?`${id}-hint`:undefined}):children;
  return <div className={`field ${wide ? "wide" : ""}`}><label htmlFor={id}><span>{label} {optional && <span className="optional" aria-hidden="true">optioneel</span>}</span></label>{control}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>;
}

export { CpvSelector as CpvEditor } from "./cpv-selector";

export function KeywordEditor({ value, onChange }: { value: Profile["keywords"]; onChange: (v: Profile["keywords"])=>void }) {
  const [input,setInput]=useState(""); const [error,setError]=useState("");
  function add() { const words=input.split(/[\n,;]+/).map(w=>w.trim()).filter(Boolean); if (!words.length || words.some(w=>w.length>150)) {setError("Voer zoektermen in van 1 tot 150 tekens.");return;} const next=[...value]; for(const keyword of words) if (!next.some(k=>k.keyword.toLowerCase()===keyword.toLowerCase())) next.push({keyword}); if(next.length>300){setError("Maximaal 300 keywords toegestaan.");return;} onChange(next);setInput("");setError(""); }
  return <div className="list-editor"><div className="list-editor-head"><h3>Zoektermen voor jouw opdrachten</h3><p>Bijvoorbeeld: data engineering, Python, ICT-detachering</p></div><div className="list-body"><div className="inline-add"><Field label="Keywords" hint="Meerdere termen? Scheid ze met een komma of puntkomma."><input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();add();}}}/></Field><button className="button secondary" type="button" onClick={add}><Plus size={17}/>Toevoegen</button></div>{error && <p className="notice error" role="alert">{error}</p>}{value.map((item,index)=><div className="item-row" key={index}><input aria-label={`Keyword ${index+1}`} maxLength={150} value={item.keyword} onChange={e=>onChange(value.map((v,i)=>i===index?{...v,keyword:e.target.value}:v))}/><button className="icon-button" type="button" aria-label={`Verwijder keyword ${item.keyword}`} onClick={()=>onChange(value.filter((_,i)=>i!==index))}><Trash2 size={17}/></button></div>)}</div></div>;
}

export function HistoryEditor({ value,onChange }: { value: Profile["historical_tenders"]; onChange: (v: Profile["historical_tenders"])=>void }) {
  const [input,setInput]=useState(""); const [error,setError]=useState("");
  function add() { const {values,invalid}=parsePublications(input,value.map(v=>v.publication_id)); if(value.length+values.length>500){setError("Maximaal 500 historische publicaties toegestaan.");return;} onChange([...value,...values.map(v=>({...v,notes:""}))]);setInput(invalid.join("\n"));setError(invalid.length?`Niet herkend: ${invalid.join(", ")}. Gebruik een publicatie-ID of een volledige https://www.tenderned.nl/aankondigingen/overzicht/ID URL.`:""); }
  return <div className="list-editor"><div className="list-editor-head"><h3>Aan deelgenomen</h3><p>Opdrachten waarop je daadwerkelijk hebt ingeschreven.</p></div><div className="list-body"><Field label="Publicaties toevoegen: aan deelgenomen" hint="Plak ID’s of URL’s, ook meerdere regels uit Excel. Dubbele publicaties worden verwijderd."><textarea value={input} onChange={e=>setInput(e.target.value)} placeholder={"123456\nhttps://www.tenderned.nl/aankondigingen/overzicht/234567/publicatie"}/></Field><button type="button" className="button secondary" onClick={add}><Plus size={17}/>Publicaties toevoegen</button>{error && <div className="notice error" role="alert">{error}</div>}{value.map((item,index)=><div className="history-row" key={item.publication_id}><header><a href={`https://www.tenderned.nl/aankondigingen/overzicht/${item.publication_id}/publicatie`} target="_blank" rel="noopener noreferrer">Publicatie {item.publication_id}</a><button className="icon-button" type="button" aria-label={`Verwijder publicatie ${item.publication_id}`} onClick={()=>onChange(value.filter((_,i)=>i!==index))}><Trash2 size={17}/></button></header><Field label={`Toelichting bij ${item.publication_id}`} optional><textarea maxLength={4000} value={item.notes} onChange={e=>onChange(value.map((v,i)=>i===index?{...v,notes:e.target.value}:v))} placeholder="Wat was jullie bijdrage aan deze opdracht?"/></Field></div>)}</div></div>;
}
