"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, Clock3, Download, FileCheck2, PauseCircle } from "lucide-react";
import { getSupabase } from "@/lib/supabase/client";
import { loadWorkspace, saveWorkspace } from "@/lib/supabase/queries";
import type { Workspace } from "@/lib/validation/profile";
import { scannerExport } from "@/lib/export/config";
import { Review } from "../onboarding/review";

const statuses = {
  pending: ["Profiel in voorbereiding", "Vul je zoekprofiel aan en bevestig je aanmelding. Je proefperiode is nog niet gestart."],
  submitted: ["Aanmelding ontvangen", "Je profiel is ingediend. We stellen je persoonlijke scanner handmatig in. Je proefperiode start pas na activering."],
  active: ["Scanner handmatig geactiveerd", "Je scanner is door de beheerder geactiveerd. Hieronder zie je de ingestelde proefdatums."],
  expired: ["Proefperiode afgelopen", "Je gratis proefperiode is afgerond. Er volgt geen automatische betaling of verlenging."],
  disabled: ["Account uitgeschakeld", "Je kunt je gegevens nog bekijken en downloaden. Neem contact op met de beheerder voor wijzigingen."],
};
const date=(s:string|null)=>s?new Date(s).toLocaleDateString("nl-NL",{day:"numeric",month:"long",year:"numeric"}):"Nog niet ingesteld";
export function Dashboard() {
  const router=useRouter();
  const [w,setW]=useState<Workspace|null>(null);const [error,setError]=useState("");const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);
  const [frequency,setFrequency]=useState(7);const [email,setEmail]=useState("");
  async function load(){setError("");try{const data=await loadWorkspace();setW(data);setFrequency(data.profile.search.email_frequency_days);setEmail(data.profile.search.notification_email);}catch(e){setError((e as Error).message);}}
  useEffect(()=>{let alive=true;loadWorkspace().then(data=>{if(!alive)return;setW(data);setFrequency(data.profile.search.email_frequency_days);setEmail(data.profile.search.notification_email);}).catch(e=>{if(alive)setError((e as Error).message);});return()=>{alive=false;};},[]);
  async function updatePreferences(){if(!w)return;setBusy(true);setError("");setMessage("");try{const profile={...w.profile,search:{...w.profile.search,email_frequency_days:frequency as 1|2|3|7|14,notification_email:email}};const result=await saveWorkspace(profile,w.revision);setW(result);setMessage("Je e-mailvoorkeuren zijn opgeslagen.");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  function download(){if(!w)return;try{const url=URL.createObjectURL(new Blob([JSON.stringify(scannerExport(w),null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="mijn-zoekprofiel.json";a.click();URL.revokeObjectURL(url);}catch(e){setError((e as Error).message);}}
  async function deletion(){if(!confirm("Wil je de beheerder verzoeken je account en bedrijfsgegevens te verwijderen? Dit wordt handmatig afgehandeld."))return;setBusy(true);setError("");try{const {error}=await getSupabase()!.rpc("request_account_deletion");if(error)throw error;setMessage("Je verwijderverzoek is geregistreerd. De beheerder handelt dit handmatig af.");}catch{setError("Het verzoek kon niet worden opgeslagen. Probeer het opnieuw of gebruik het contactadres op de privacypagina.");}finally{setBusy(false);}}
  if(!w)return error?<div className="notice error" role="alert">{error}<p><button className="button secondary" onClick={load}>Opnieuw laden</button></p></div>:<div className="loading" role="status"><span className="spinner"/><p>Je overzicht ophalen…</p></div>;
  const [statusTitle,statusText]=statuses[w.subscription.status]; const disabled=w.subscription.status==="disabled";
  return <><div className="dashboard-hero"><div><div className="eyebrow">Mijn account</div><h1>{w.profile.company.company_name||"Jouw bedrijf, jouw profiel."}</h1><p>Laatst bijgewerkt: {new Date(w.updated_at).toLocaleString("nl-NL")}</p></div>{!disabled&&<Link className="button" href="/onboarding/">{w.onboarding_completed?"Zoekprofiel wijzigen":"Profiel verder invullen"}</Link>}</div>
    <div className="status-banner">{w.subscription.status==="active"?<CheckCircle2 size={23}/>:disabled?<PauseCircle size={23}/>:<Clock3 size={23}/>}<div><h2>{statusTitle}</h2><p>{statusText}</p></div></div>
    {error&&<div className="notice error" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}
    <div className="dashboard-grid"><div><section className="panel"><h2>Je profiel in het kort</h2><p>{w.profile.search.business_description||"Vertel ons wat je bedrijf doet. Dat vormt de basis voor jouw persoonlijke zoekprofiel."}</p><dl className="summary-dl"><dt>CPV-codes</dt><dd>{w.profile.cpv_codes.length}</dd><dt>Positieve keywords</dt><dd>{w.profile.keywords.filter(k=>k.type==="positive").length}</dd><dt>Uitsluitingstermen</dt><dd>{w.profile.keywords.filter(k=>k.type==="negative").length}</dd><dt>Eerdere publicaties</dt><dd>{w.profile.historical_tenders.length}</dd><dt>Onboarding</dt><dd>{w.onboarding_completed?"Afgerond":"Nog aan te vullen"}</dd></dl><div className="dashboard-actions"><button className="button secondary" onClick={download}><Download size={16}/>Eigen gegevens downloaden</button></div></section>
      <section className="panel"><h2>Alle ingevulde gegevens</h2><details><summary>Bekijk je volledige bedrijfs- en zoekprofiel</summary><Review profile={w.profile} edit={step=>router.push(`/onboarding/?stap=${step+1}`)}/></details></section>
    </div><div><section className="panel"><h2>Gratis proefperiode</h2><dl className="summary-dl"><dt>Status</dt><dd>{statusTitle}</dd><dt>Begindatum</dt><dd>{date(w.subscription.trial_started_at)}</dd><dt>Einddatum</dt><dd>{date(w.subscription.trial_ends_at)}</dd></dl>{w.subscription.status==="active"&&w.subscription.trial_ends_at&&new Date(w.subscription.trial_ends_at)<new Date()&&<p>De ingestelde einddatum is verstreken. Er is geen automatische verlenging.</p>}<p>De beheerder stelt deze datums handmatig in. Er is geen betaalfunctie.</p></section>
      <section className="panel"><h2>Jouw e-mailvoorkeuren</h2><label className="field"><span>Frequentie</span><select disabled={busy||disabled} value={frequency} onChange={e=>setFrequency(Number(e.target.value))}>{[[1,"Dagelijks"],[2,"Iedere 2 dagen"],[3,"Iedere 3 dagen"],[7,"Wekelijks"],[14,"Iedere 14 dagen"]].map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><label className="field"><span>Ontvangstadres</span><input disabled={busy||disabled} type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><button disabled={busy||disabled} className="button secondary full" onClick={updatePreferences}>Voorkeuren opslaan</button></section>
      <section className="panel"><FileCheck2 size={23}/><h2 style={{marginTop:15}}>Jij houdt de regie</h2><p>Je kunt je gegevens downloaden of een verzoek tot accountverwijdering indienen.</p><button className="text-link" disabled={busy} style={{background:"none",border:0,padding:0}} onClick={deletion}>Accountverwijdering aanvragen</button></section>
    </div></div></>;
}
