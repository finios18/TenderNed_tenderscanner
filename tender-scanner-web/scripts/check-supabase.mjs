// Alleen-lezen verbindingscontrole; maakt geen account aan en verstuurt geen mail.
import { createRequire } from "node:module";
const require=createRequire(import.meta.url);
const {loadEnvConfig}=createRequire(require.resolve("next/package.json"))("@next/env");
loadEnvConfig(process.cwd(),true);
const base=process.env.NEXT_PUBLIC_SUPABASE_URL;
const key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
if(!base||!key)throw new Error("Supabase-configuratie ontbreekt.");
const headers={apikey:key,"Content-Type":"application/json"};
async function request(path,options={}) {
  const response=await fetch(new URL(path,base),{...options,headers,signal:AbortSignal.timeout(15000)});
  const body=await response.json();return {response,body};
}
const {response,body}=await request("/auth/v1/settings");
if(!response.ok)throw new Error(`Authenticatieverbinding mislukt (HTTP ${response.status}).`);
console.log("Supabase-project bereikbaar; publieke sleutel geaccepteerd.");
console.log(`E-mailregistratie: ${body.external?.email===true?"ingeschakeld":"controleer dashboard"}`);
console.log(`E-mailbevestiging: ${body.mailer_autoconfirm===false?"vereist":"controleer dashboard: automatische bevestiging staat mogelijk aan"}`);
const tables=["profiles","companies","search_profiles","cpv_codes","keywords","historical_tenders","subscriptions","cpv_catalog"];
for(const table of tables){
  const {response,body}=await request(`/rest/v1/${table}?select=*&limit=1`);
  if(![401,403].includes(response.status)||body.code!=="42501")throw new Error(`Controle van ${table} mislukt (HTTP ${response.status}, ${body.code??"geen code"}). Verwacht een toegangsweigering voor anoniem verkeer.`);
  console.log(`Tabel ${table}: anonieme toegang geweigerd.`);
}
for(const name of ["get_workspace","save_onboarding","admin_export_config","get_cpv_catalog_info"]){
  const payload=name==="save_onboarding"?{payload:{},complete:false,expected_revision:0}:name==="admin_export_config"?{customer_id:"00000000-0000-4000-8000-000000000000"}:{};
  const {response,body}=await request(`/rest/v1/rpc/${name}`,{method:"POST",body:JSON.stringify(payload)});
  if(![401,403].includes(response.status)||body.code!=="42501")throw new Error(`Functie ${name} ontbreekt of heeft onverwachte rechten (HTTP ${response.status}, ${body.code??"geen code"}).`);
  console.log(`Functie ${name}: aanwezig, anonieme toegang geweigerd.`);
}
console.log("Verbindingscontrole geslaagd. Inloggen en opslag met een echte gebruiker moeten apart worden getest.");
