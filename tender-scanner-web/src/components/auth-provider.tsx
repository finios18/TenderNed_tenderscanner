"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { getSupabase } from "@/lib/supabase/client";
const AuthContext = createContext<{ user: User | null; loading: boolean; configured: boolean }>({ user: null, loading: true, configured: false });
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const client = getSupabase();
  useEffect(() => {
    if (!client) { queueMicrotask(() => setLoading(false)); return; }
    let mounted = true;
    client.auth.getUser().then(({ data }) => { if (mounted) { setUser(data.user); setLoading(false); } }).catch(() => { if (mounted) setLoading(false); });
    const { data } = client.auth.onAuthStateChange((_event, session) => { setUser(session?.user ?? null); setLoading(false); });
    return () => { mounted = false; data.subscription.unsubscribe(); };
  }, [client]);
  return <AuthContext.Provider value={{ user, loading, configured: !!client }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
