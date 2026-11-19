import { z } from "zod";
import { getCpv } from "../cpv";

const text = z.string().max(12000, "Gebruik maximaal 12.000 tekens.");
const short = z.string().max(250, "Gebruik maximaal 250 tekens.");
const email = z.union([z.literal(""), z.email("Vul een geldig e-mailadres in.")]);
const money = z.number().finite().min(0).max(1_000_000_000_000).nullable();
export const cpvPattern = /^\d{8}(?:-\d)?$/;
export const publicationPattern = /^[1-9]\d{0,11}$/;
export const storedProfileSchema = z.object({
  company: z.object({
    company_name: short, website: z.string().max(2048).refine(value => {
      if (!value) return true;
      try { return ["https:", "http:"].includes(new URL(value).protocol); } catch { return false; }
    }, "Gebruik een volledige http:// of https:// URL."),
    kvk_number: z.string().regex(/^(?:\d{8})?$/, "Een KvK-nummer bestaat uit acht cijfers."),
    contact_person: short, contact_email: email, phone_number: z.string().max(50), city: short,
    company_size: z.enum(["", "1", "2–10", "11–50", "51–250", "251+"]),
  }).strict(),
  search: z.object({
    business_description: text, services_description: text, specializations: text, sectors: text,
    desired_contracts: text, excluded_services: text, competitive_advantages: text,
    geographic_preferences: text, minimum_contract_value: money, maximum_contract_value: money,
    preferred_contract_types: text, preferred_buyers: text, certifications: text,
    additional_requirements: text, cpv_notes: text, email_notes: text,
    email_frequency_days: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(7), z.literal(14)]),
    notification_email: email,
  }).strict(),
  cpv_codes: z.array(z.object({ code: z.string().regex(cpvPattern, "Gebruik een geldige CPV-code."), description: short,
    include_descendants: z.boolean().optional(), original_description: z.string().max(12000).nullable().optional(),
  }).strict()).max(150),
  keywords: z.array(z.object({ keyword: z.string().trim().min(1).max(150), type: z.enum(["positive", "negative"]) }).strict()).max(300),
  historical_tenders: z.array(z.object({ publication_id: z.string().regex(publicationPattern), original_input: z.string().max(2048),
    category: z.enum(["participated", "interesting", "not_interesting"]), notes: z.string().max(4000) }).strict()).max(500),
}).strict();
export const profileSchema = storedProfileSchema.superRefine((data, ctx) => {
  data.cpv_codes.forEach((selection,index) => {
    if (!getCpv(selection.code)) ctx.addIssue({ code: "custom", path: ["cpv_codes",index,"code"], message: `CPV-code ${selection.code} bestaat niet in de officiële CPV 2008-basiswoordenlijst. Verwijder of vervang deze selectie.` });
  });
  const { minimum_contract_value: min, maximum_contract_value: max } = data.search;
  if (min !== null && max !== null && min > max) ctx.addIssue({ code: "custom", path: ["search", "maximum_contract_value"], message: "De maximale waarde moet minstens de minimale waarde zijn." });
  if (new Set(data.cpv_codes.map(c => c.code.split("-")[0])).size !== data.cpv_codes.length)
    ctx.addIssue({ code: "custom", path: ["cpv_codes"], message: "Een CPV-code staat dubbel in de whitelist." });
  if (new Set(data.keywords.map(k => `${k.type}:${k.keyword.toLowerCase()}`)).size !== data.keywords.length)
    ctx.addIssue({ code: "custom", path: ["keywords"], message: "Een keyword staat dubbel in dezelfde categorie." });
  if (new Set(data.historical_tenders.map(t => `${t.category}:${t.publication_id}`)).size !== data.historical_tenders.length)
    ctx.addIssue({ code: "custom", path: ["historical_tenders"], message: "Een publicatie staat dubbel in dezelfde categorie." });
});
export type Profile = z.infer<typeof profileSchema>;
export type Subscription = { status: "pending" | "submitted" | "active" | "expired" | "disabled"; trial_started_at: string | null; trial_ends_at: string | null; activated_at: string | null };
export type Workspace = { company_id: string; revision: number; updated_at: string; onboarding_completed: boolean; subscription: Subscription; profile: Profile };

export const emptyProfile: Profile = {
  company: { company_name: "", website: "", kvk_number: "", contact_person: "", contact_email: "", phone_number: "", city: "", company_size: "" },
  search: { business_description: "", services_description: "", specializations: "", sectors: "", desired_contracts: "", excluded_services: "", competitive_advantages: "", geographic_preferences: "", minimum_contract_value: null, maximum_contract_value: null, preferred_contract_types: "", preferred_buyers: "", certifications: "", additional_requirements: "", cpv_notes: "", email_notes: "", email_frequency_days: 7, notification_email: "" },
  cpv_codes: [], keywords: [], historical_tenders: [],
};

export function validateCompletion(profile: Profile): string[] {
  const errors: string[] = [];
  const parsed = profileSchema.safeParse(profile);
  if (!parsed.success) errors.push(...parsed.error.issues.map(issue => issue.message));
  if (!profile.company.company_name.trim()) errors.push("Vul je bedrijfsnaam in.");
  if (!profile.search.business_description.trim()) errors.push("Beschrijf kort wat je bedrijf doet.");
  if (!profile.search.notification_email) errors.push("Vul een ontvangstadres in.");
  return errors;
}
