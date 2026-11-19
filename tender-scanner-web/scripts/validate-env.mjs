// Voorkom per ongeluk publiceren van een beheersleutel in NEXT_PUBLIC-variabelen.
import { createRequire } from "node:module";
const require=createRequire(import.meta.url);
const {loadEnvConfig}=createRequire(require.resolve("next/package.json"))("@next/env");
loadEnvConfig(process.cwd(),process.argv.includes("--dev"));
const url=process.env.NEXT_PUBLIC_SUPABASE_URL??"";
const key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY??"";
if(Boolean(url)!==Boolean(key))throw new Error("Stel zowel de Supabase-project-URL als de publieke sleutel in, of laat beide leeg voor een publieke preview.");
if(key){
  if(key.startsWith("sb_secret_"))throw new Error("Een geheime Supabase-sleutel mag nooit NEXT_PUBLIC zijn.");
  if(key.split(".").length===3){
    let payload;
    try{payload=JSON.parse(Buffer.from(key.split(".")[1],"base64url").toString());}catch{throw new Error("De publieke Supabase-sleutel is ongeldig.");}
    if(payload.role!=="anon")throw new Error("Gebruik uitsluitend de publieke anon/publishable key, geen service_role JWT.");
  }else if(!key.startsWith("sb_publishable_"))throw new Error("Gebruik een Supabase publishable key of legacy anon JWT.");
  const parsed=new URL(url);
  if(parsed.protocol!=="https:"&&!(["localhost","127.0.0.1"].includes(parsed.hostname)&&parsed.protocol==="http:"))throw new Error("Gebruik HTTPS voor het Supabase-project.");
}
