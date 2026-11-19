"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Check, ShieldCheck } from "lucide-react";
import { z } from "zod";
import { getSupabase } from "@/lib/supabase/client";
import { useAuth } from "./auth-provider";
import { SiteShell } from "./site-shell";

type Mode = "register" | "login" | "reset" | "password";
const labels = { register: ["Maak ruimte voor de juiste opdrachten.", "Start je gratis proefperiode", "Account aanmaken"], login: ["Welkom terug.", "Inloggen", "Inloggen"], reset: ["We helpen je weer op weg.", "Wachtwoord vergeten?", "Stuur herstellink"], password: ["Een nieuwe start.", "Nieuw wachtwoord instellen", "Wachtwoord opslaan"] };
export function AuthForm({ mode }: { mode: Mode }) {
  const { configured, user } = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const router = useRouter(); const text = labels[mode];
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setMessage("");
    const client = getSupabase(); if (!client) return;
    if (mode !== "password" && !z.email().safeParse(email).success) { setError("Vul een geldig e-mailadres in."); return; }
    if (["register","password"].includes(mode) && password.length < 12) { setError("Gebruik een wachtwoord van minstens 12 tekens."); return; }
    if (mode === "register" && !consent) { setError("Lees de privacy-informatie en bevestig je aanmelding."); return; }
    setBusy(true);
    try {
      if (mode === "register") {
        const { data, error } = await client.auth.signUp({ email, password, options: { emailRedirectTo: `${location.origin}/auth/callback/` } });
        if (error) throw error;
        if (data.session && data.user?.email_confirmed_at) router.replace("/onboarding/");
        else setMessage("Als dit adres kan worden aangemeld, ontvang je een verificatiemail. Open de link in dezelfde browser als waarin je je aanmeldt. Controleer ook je spammap.");
      } else if (mode === "login") {
        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error || !data.user?.email_confirmed_at) { setError("Inloggen is niet gelukt. Controleer je gegevens en verifieer eerst je e-mailadres."); return; }
        router.replace("/dashboard/");
      } else if (mode === "reset") {
        const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: `${location.origin}/auth/callback/?next=password` });
        if (error) throw error;
        setMessage("Als er een account bij dit adres hoort, ontvang je een herstellink. Open de link in dezelfde browser.");
      } else {
        if (!user) { setError("Open eerst de herstellink uit je e-mail of log in."); return; }
        const { error } = await client.auth.updateUser({ password }); if (error) throw error;
        setPassword(""); setMessage("Je wachtwoord is gewijzigd. Je kunt naar je dashboard.");
      }
    } catch { setError("De aanvraag is niet gelukt. Probeer het later opnieuw. Mogelijk is de e-maillimiet bereikt."); }
    finally { setBusy(false); }
  }
  async function resend() {
    const client = getSupabase(); if (!client || !z.email().safeParse(email).success) { setError("Vul eerst je e-mailadres in."); return; }
    setBusy(true); setError("");
    try { const { error } = await client.auth.resend({ type: "signup", email, options: { emailRedirectTo: `${location.origin}/auth/callback/` } }); if (error) throw error; setMessage("Als dit adres nog verificatie nodig heeft, ontvang je een nieuwe link."); }
    catch { setError("Een nieuwe link aanvragen is nu niet gelukt. Wacht even en probeer opnieuw."); } finally { setBusy(false); }
  }
  return <SiteShell><main className="auth-page" id="main"><section className="auth-intro"><div className="eyebrow">Jouw persoonlijke aanbestedingsprofiel</div><h1>{text[0]}</h1><p>Je bedrijf is meer dan een paar zoektermen. Maak een profiel dat vertelt wat écht bij je past.</p><ul><li><Check size={18}/>Bewaar en bewerk je profiel op je eigen tempo</li><li><Check size={18}/>14 dagen proberen vanaf handmatige activering</li><li><ShieldCheck size={18}/>Geen betaalgegevens nodig</li></ul></section><section className="form-card"><h2>{text[1]}</h2><p className="intro">{mode === "register" ? "Begin met je e-mailadres. Na verificatie stel je je bedrijfsprofiel samen." : "Ga veilig verder met je eigen account."}</p>
    {!configured && <div className="notice info" role="status">Aanmelden is nog niet beschikbaar. De beheerder moet de accountomgeving eerst verbinden.</div>}
    <form onSubmit={submit}>{mode !== "password" && <label className="field"><span>E-mailadres</span><input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="jij@bedrijf.nl"/></label>}
    {mode !== "reset" && <div className="field"><label htmlFor="account-password"><span>Wachtwoord</span></label><input id="account-password" type="password" required minLength={mode === "login" ? 1 : 12} autoComplete={mode === "login" ? "current-password" : "new-password"} aria-describedby={mode!=="login"?"password-hint":undefined} value={password} onChange={e=>setPassword(e.target.value)}/>{mode !== "login" && <small id="password-hint">Gebruik minimaal 12 tekens, liefst een unieke wachtwoordzin.</small>}</div>}
    {mode === "register" && <label className="checkbox"><input type="checkbox" required checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Ik heb de <Link className="text-link" href="/privacy/">privacy-informatie</Link> gelezen en meld mijn bedrijf aan voor de pilot.</span></label>}
    {error && <div className="notice error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    <button disabled={busy || !configured} className="button full" type="submit">{busy ? "Even geduld…" : text[2]}</button></form>
    {mode === "register" && <><p className="form-footer">Al een account? <Link href="/inloggen/">Log in</Link></p><button className="text-link" style={{background:"none",border:0,padding:0}} disabled={busy || !configured} onClick={resend}>Verificatiemail opnieuw aanvragen</button></>}
    {mode === "login" && <><p className="form-footer"><Link href="/wachtwoord-vergeten/">Wachtwoord vergeten?</Link></p><p className="form-footer">Nieuw hier? <Link href="/registreren/">Maak een account</Link></p></>}
    {mode === "reset" && <p className="form-footer"><Link href="/inloggen/">Terug naar inloggen</Link></p>}
    {mode === "password" && <p className="form-footer"><Link href="/dashboard/">Naar je dashboard</Link></p>}
  </section></main></SiteShell>;
}
