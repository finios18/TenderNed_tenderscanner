"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useAuth } from "./auth-provider";
import { SiteShell } from "./site-shell";
import { getSupabase } from "@/lib/supabase/client";
export function AccountShell({ children }: { children: ReactNode }) {
  const { user, loading, configured } = useAuth(); const router=useRouter();
  const [logoutError,setLogoutError]=useState("");
  useEffect(()=>{ if (!loading && configured && !user) router.replace("/inloggen/"); },[loading,configured,user,router]);
  return <SiteShell><main id="main" className="account-bg"><div className="account-wrap">
    {!configured ? <div className="notice info">De accountomgeving is nog niet aangesloten. Je kunt wel de <Link href="/">uitleg over de pilot bekijken</Link>.</div> : loading || !user ? <div className="loading" role="status"><span className="spinner"/><p>Je account wordt geladen…</p></div> : !user.email_confirmed_at ? <div className="notice info">Verifieer eerst je e-mailadres via de link in je inbox.</div> : <><div className="account-top"><span>{user.email}</span><div className="account-nav"><Link href="/dashboard/">Mijn overzicht</Link><Link href="/onboarding/">Zoekprofiel</Link><button className="icon-button" aria-label="Uitloggen" onClick={async()=>{ const { error } = await getSupabase()!.auth.signOut(); if (error) setLogoutError("Uitloggen is niet gelukt. Probeer het opnieuw."); /* De auth-effect hierboven verzorgt de enige redirect. */ }}><LogOut size={17}/></button></div></div>{logoutError&&<div className="notice error" role="alert">{logoutError}</div>}{children}</>}
  </div></main></SiteShell>;
}
