"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Save } from "lucide-react";
import { loadWorkspace,saveWorkspace } from "@/lib/supabase/queries";
import { emptyProfile, type Profile, type Workspace } from "@/lib/validation/profile";
import { CpvEditor,Field,HistoryEditor,KeywordEditor } from "./editors";
import { businessFields,companyLabels,preferenceFields,stepLabels } from "./fields";
import { Review } from "./review";

const descriptions = [
  "Begin bij de basis. Je kunt je gegevens later altijd aanpassen. Alleen je bedrijfsnaam is bij afronding verplicht.",
  "Vertel in je eigen woorden waar je goed in bent. Dit vormt straks de context voor jouw persoonlijke scanner.",
  "CPV-codes beschrijven het soort producten of diensten in een aanbesteding. Voeg toe wat past; de whitelist mag voorlopig leeg blijven.",
  "Welke woorden wijzen op een goede match? En welke woorden zijn juist een signaal dat een opdracht minder goed past?",
  "Concrete voorbeelden vertellen veel. Voeg zo veel relevante voorbeelden toe als je wilt, tot 500 publicaties. We slaan ze alleen op; er worden hier geen documenten geanalyseerd.",
  "Geef aan waar en onder welke voorwaarden je graag werkt. Laat onbekende bedragen gerust leeg.",
  "Kies het ritme en adres voor je toekomstige aanbestedingsmail. De website verstuurt nog geen rapporten; we gebruiken dit bij de handmatige inrichting.",
  "Controleer je profiel. Na bevestiging ontvangen wij je aanmelding en stellen we de scanner handmatig in.",
];
export function Wizard() {
  const [workspace,setWorkspace]=useState<Workspace|null>(null);const [profile,setProfile]=useState<Profile>(structuredClone(emptyProfile));
  const [step,setStep]=useState(0);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);
  const [dirty,setDirty]=useState(false);const [error,setError]=useState("");const [saved,setSaved]=useState("");const [confirmed,setConfirmed]=useState(false);
  const heading=useRef<HTMLHeadingElement>(null);const router=useRouter();
  async function load() {setLoading(true);setError("");try{const w=await loadWorkspace();setWorkspace(w);setProfile(w.profile);setDirty(false);}catch(e){setError((e as Error).message);}finally{setLoading(false);}}
  useEffect(()=>{let alive=true;loadWorkspace().then(w=>{if(!alive)return;setWorkspace(w);setProfile(w.profile);const requested=Number(new URLSearchParams(location.search).get("stap"));if(requested>=1&&requested<=8)setStep(requested-1);}).catch(e=>{if(alive)setError((e as Error).message);}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[]);
  useEffect(()=>{const prevent=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue="";}};window.addEventListener("beforeunload",prevent);return()=>window.removeEventListener("beforeunload",prevent);},[dirty]);
  useEffect(()=>{const prevent=(e:MouseEvent)=>{const a=(e.target as HTMLElement).closest("a[href]");if(dirty&&a&&!confirm("Je hebt niet-opgeslagen wijzigingen. Wil je deze pagina toch verlaten?")){e.preventDefault();e.stopPropagation();}};document.addEventListener("click",prevent,true);return()=>document.removeEventListener("click",prevent,true);},[dirty]);
  function change(next: Profile) {setProfile(next);setDirty(true);setSaved("");setError("");}
  function company(key:keyof Profile["company"],value:string) {change({...profile,company:{...profile.company,[key]:value}});}
  function search(key:keyof Profile["search"],value:string|number|null) {change({...profile,search:{...profile.search,[key]:value}});}
  function go(next:number) {setStep(next);setError("");requestAnimationFrame(()=>heading.current?.focus());}
  async function save(nextStep?:number,complete=false) {
    if(busy || !workspace)return;setBusy(true);setError("");
    try{const result=await saveWorkspace(profile,workspace.revision,complete);setWorkspace(result);setDirty(false);setSaved(`Opgeslagen om ${new Date().toLocaleTimeString("nl-NL",{hour:"2-digit",minute:"2-digit"})}`);if(complete)router.push("/dashboard/?aangemeld=1");else if(nextStep!==undefined)go(nextStep);}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  if(loading)return <div className="loading" role="status"><span className="spinner"/><p>Je zoekprofiel ophalen…</p></div>;
  if(!workspace)return <div className="notice error" role="alert">{error}<p><button className="button secondary" onClick={load}>Opnieuw proberen</button></p></div>;
  const disabled=workspace.subscription.status==="disabled";
  return <div className="onboard-layout"><aside className="steps-nav"><div className="eyebrow">Jouw persoonlijke zoekprofiel</div><h2>Vertel wat bij je past.</h2><ol>{stepLabels.map((label,index)=><li key={label}><button type="button" className={step===index?"selected":""} aria-current={step===index?"step":undefined} onClick={()=>go(index)} disabled={busy}><span className="step-num">{index<step?<Check size={14}/>:index+1}</span><span className="step-name">{label}</span></button></li>)}</ol><div className="progress-track" role="progressbar" aria-valuenow={step+1} aria-valuemin={1} aria-valuemax={8} aria-label="Stap van de vragenlijst"><div className="progress-fill" style={{width:`${(step+1)/8*100}%`}}/></div><p className="save-hint">Stap {step+1} van 8 · {dirty?"Niet-opgeslagen wijzigingen":saved||"Je gegevens zijn opgeslagen"}</p></aside>
  <section className="onboard-card"><div className="eyebrow">{step===7?"Bijna klaar":"Je profiel, stap voor stap"}</div><h1 ref={heading} tabIndex={-1}>{stepLabels[step]}</h1><p className="intro">{descriptions[step]}</p>{disabled&&<div className="notice info">Je account is uitgeschakeld. Je profiel blijft in te zien, maar kan niet worden gewijzigd.</div>}
  <fieldset disabled={busy||disabled} style={{border:0,padding:0,margin:0,minWidth:0}}>
  {step===0&&<div className="field-grid">{Object.entries(companyLabels).map(([key,label])=><Field key={key} label={label} optional={key!=="company_name"} wide={key==="company_name"||key==="website"}>{key==="company_size"?<select value={profile.company.company_size} onChange={e=>company("company_size",e.target.value)}><option value="">Maak een keuze</option>{["1","2–10","11–50","51–250","251+"].map(v=><option value={v} key={v}>{v} medewerker{v==="1"?"":"s"}</option>)}</select>:<input type={key==="contact_email"?"email":key==="website"?"url":key==="phone_number"?"tel":"text"} autoComplete={key==="company_name"?"organization":key==="contact_person"?"name":key==="contact_email"?"email":"off"} maxLength={key==="kvk_number"?8:key==="website"?2048:key==="phone_number"?50:250} value={profile.company[key as keyof Profile["company"]]} onChange={e=>company(key as keyof Profile["company"],e.target.value)} placeholder={key==="website"?"https://jouwbedrijf.nl":undefined}/>}</Field>)}</div>}
  {step===1&&businessFields.map(([key,label,hint])=><Field label={label} hint={hint} key={key} optional={key!=="business_description"}><textarea maxLength={12000} value={profile.search[key]} onChange={e=>search(key,e.target.value)}/></Field>)}
  {step===2&&<><CpvEditor value={profile.cpv_codes} onChange={v=>change({...profile,cpv_codes:v})}/><Field label="Aanvullende CPV-opmerkingen" optional><textarea maxLength={12000} value={profile.search.cpv_notes} onChange={e=>search("cpv_notes",e.target.value)} placeholder="Twijfel je over codes of wil je iets toelichten?"/></Field></>}
  {step===3&&<>{(["positive","negative"] as const).map(type=><KeywordEditor key={type} type={type} value={profile.keywords} onChange={v=>change({...profile,keywords:v})}/>)}</>}
  {step===4&&<>{(["participated","interesting","not_interesting"] as const).map(category=><HistoryEditor key={category} category={category} value={profile.historical_tenders} onChange={v=>change({...profile,historical_tenders:v})}/>)}</>}
  {step===5&&<><div className="field-grid"><Field label="Minimale opdrachtwaarde (€)" optional><input type="number" min={0} max={1e12} value={profile.search.minimum_contract_value??""} onChange={e=>search("minimum_contract_value",e.target.value===""?null:Number(e.target.value))}/></Field><Field label="Maximale opdrachtwaarde (€)" optional><input type="number" min={0} max={1e12} value={profile.search.maximum_contract_value??""} onChange={e=>search("maximum_contract_value",e.target.value===""?null:Number(e.target.value))}/></Field></div>{preferenceFields.map(([key,label,hint])=><Field key={key} label={label} hint={hint} optional><textarea maxLength={12000} value={profile.search[key]} onChange={e=>search(key,e.target.value)}/></Field>)}</>}
  {step===6&&<><Field label="Ontvangstfrequentie"><select value={profile.search.email_frequency_days} onChange={e=>search("email_frequency_days",Number(e.target.value))}>{[[1,"Dagelijks"],[2,"Iedere 2 dagen"],[3,"Iedere 3 dagen"],[7,"Wekelijks"],[14,"Iedere 14 dagen"]].map(([n,label])=><option value={n} key={n}>{label}</option>)}</select></Field><Field label="Ontvangstadres" hint="Dit mag afwijken van het e-mailadres waarmee je inlogt."><input type="email" maxLength={320} autoComplete="email" value={profile.search.notification_email} onChange={e=>search("notification_email",e.target.value)}/></Field><Field label="Opmerkingen bij de mailvoorkeuren" optional><textarea maxLength={12000} value={profile.search.email_notes} onChange={e=>search("email_notes",e.target.value)}/></Field><div className="notice info">Je voorkeur wordt opgeslagen voor de handmatige inrichting. Er worden nog geen aanbestedingsmails vanuit deze website verstuurd.</div></>}
  {step===7&&<><Review profile={profile} edit={go}/><label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>Ik heb mijn gegevens gecontroleerd en wil mijn aanmelding indienen voor handmatige inrichting.</span></label></>}
  </fieldset>
  {error&&<div className="notice error" role="alert">{error}</div>}{saved&&<div role="status" className="notice">{saved}</div>}
  <div className="onboard-actions"><button className="button secondary" disabled={busy||disabled} onClick={()=>save()}><Save size={16}/>Tussentijds opslaan</button><div>{step>0&&<button className="button secondary" disabled={busy} onClick={()=>go(step-1)}>Vorige</button>}{step<7?<button className="button" disabled={busy||disabled} onClick={()=>save(step+1)}>{busy?"Opslaan…":"Bewaar en verder"}</button>:<button className="button" disabled={busy||disabled||!confirmed} onClick={()=>save(undefined,true)}>{busy?"Aanmelding opslaan…":"Aanmelding bevestigen"}</button>}</div></div>
  </section></div>;
}
