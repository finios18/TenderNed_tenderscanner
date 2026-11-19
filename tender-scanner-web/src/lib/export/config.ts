import type { Workspace } from "../validation/profile";
import { cpvMetadata, expandCpvSelections, normalizeCpvSelection } from "../cpv";
export function scannerExport(workspace: Workspace) {
  const p = workspace.profile;
  const history = (category: string) => p.historical_tenders.filter(t => t.category === category).map(t => ({ publication_id: t.publication_id, original_input: t.original_input, notes: t.notes }));
  return {
    schema_version: 2, customer_id: workspace.company_id,
    company: { ...p.company, name: p.company.company_name, description: p.search.business_description },
    contact: { email: p.search.notification_email || p.company.contact_email, person: p.company.contact_person },
    business_context: { description: p.search.business_description, services: p.search.services_description, specializations: p.search.specializations, sectors: p.search.sectors, desired_contracts: p.search.desired_contracts, excluded_services: p.search.excluded_services, competitive_advantages: p.search.competitive_advantages },
    scanner_config: { cpv_whitelist: expandCpvSelections(p.cpv_codes), cpv_details: p.cpv_codes.map(normalizeCpvSelection),
      cpv_dataset: { classification: cpvMetadata.classification, source_sha256: cpvMetadata.source_sha256 }, cpv_notes: p.search.cpv_notes,
      keywords: p.keywords.filter(k => k.type === "positive").map(k => k.keyword), negative_keywords: p.keywords.filter(k => k.type === "negative").map(k => k.keyword),
      email_frequency_days: p.search.email_frequency_days, notification_email: p.search.notification_email, email_notes: p.search.email_notes,
      geographic_preferences: p.search.geographic_preferences, minimum_contract_value: p.search.minimum_contract_value, maximum_contract_value: p.search.maximum_contract_value,
      preferred_contract_types: p.search.preferred_contract_types, preferred_buyers: p.search.preferred_buyers, certifications: p.search.certifications, additional_requirements: p.search.additional_requirements },
    historical_tenders: { participated: history("participated"), interesting: history("interesting"), not_interesting: history("not_interesting") },
    subscription: workspace.subscription, onboarding_completed: workspace.onboarding_completed, updated_at: workspace.updated_at,
  };
}
