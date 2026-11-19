import Link from "next/link";
import { SiteShell } from "@/components/site-shell";
export default function NotFound(){return <SiteShell><main id="main" className="container privacy"><h1>Deze pagina bestaat niet.</h1><p>Ga terug naar het begin of open je account.</p><Link className="button" href="/">Naar de homepage</Link></main></SiteShell>;}
