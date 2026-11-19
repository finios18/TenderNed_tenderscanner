"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getSupabase } from "@/lib/supabase/client";
import { SiteShell } from "@/components/site-shell";
export default function Callback() {
  const [error, setError] = useState(""); const router = useRouter();
  const request = useRef<Promise<{ error: unknown }> | null>(null);
  useEffect(()=>{
    const client=getSupabase(); const params=new URLSearchParams(location.search); const code=params.get("code");
    if (!client || !code || params.has("error")) { queueMicrotask(()=>setError("De link is ongeldig of verlopen. Vraag een nieuwe link aan en open die in dezelfde browser.")); return; }
    request.current ??= client.auth.exchangeCodeForSession(code);
    request.current.then(({error})=>{ history.replaceState({},"",location.pathname); if (error) setError("Deze link kon niet worden verwerkt. Vraag een nieuwe link aan in dezelfde browser."); else router.replace(params.get("next")==="password" ? "/nieuw-wachtwoord/" : "/dashboard/"); });
  },[router]);
  return <SiteShell><main id="main" className="container privacy"><h1>Je account bevestigen</h1>{error ? <div className="notice error" role="alert">{error}<p><Link href="/registreren/">Nieuwe verificatiemail aanvragen</Link> · <Link href="/wachtwoord-vergeten/">Nieuw wachtwoord aanvragen</Link></p></div> : <p role="status">We controleren je link. Een moment geduld…</p>}</main></SiteShell>;
}
