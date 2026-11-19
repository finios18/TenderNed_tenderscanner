import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/components/auth-provider";
import "./globals.css";
export const metadata: Metadata = { title: { default: "Tenderprofiel — aanbestedingen die bij je bedrijf passen", template: "%s · Tenderprofiel" }, description: "Stel je bedrijfsprofiel samen voor een gratis proefperiode met een gepersonaliseerde TenderNed-scanner." };
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="nl" data-scroll-behavior="smooth">
      {/* Browserextensies zoals Grammarly/Monica voegen vóór hydration body-attributen toe.
          Beperk de uitzondering tot dit element; controle van onderliggende UI blijft aan. */}
      <body suppressHydrationWarning>
        <a className="skip-link" href="#main">Direct naar de inhoud</a>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
