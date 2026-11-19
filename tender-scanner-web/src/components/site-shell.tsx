import Link from "next/link";
import type { ReactNode } from "react";
import { Brand } from "./ui/brand";
export function SiteShell({ children }: { children: ReactNode }) {
  return <><header className="site-header"><div className="container header-inner"><Brand/><nav aria-label="Hoofdnavigatie"><Link className="nav-info" href="/#werkwijze">Hoe het werkt</Link><Link href="/inloggen/">Inloggen</Link><Link className="button small" href="/registreren/">Start gratis</Link></nav></div></header>{children}<footer className="footer"><div className="container footer-inner"><div><Brand/><p>Een zoekprofiel dat begint bij jouw bedrijf.</p></div><div><Link href="/privacy/">Privacy & gegevens</Link><span>Onafhankelijke pilot · geen onderdeel van TenderNed</span></div></div></footer></>;
}
