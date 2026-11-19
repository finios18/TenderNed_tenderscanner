import { getSupabase } from "./client";
import { profileSchema, storedProfileSchema, validateCompletion, type Profile, type Workspace } from "../validation/profile";
import { cpvMetadata, normalizeCpvSelection } from "../cpv";

export function friendlyError(error: { code?: string; message: string }): string {
  if (error.code === "40001") return "Je profiel is in een ander tabblad gewijzigd. Herlaad deze pagina voordat je opnieuw opslaat.";
  if (error.code === "42501") return "Je hebt geen toegang tot deze handeling. Controleer of je e-mail geverifieerd is en je account actief mag worden bewerkt.";
  if (error.code === "23505") return "Er staat een dubbele code, keyword of publicatie in je profiel.";
  return "Opslaan is niet gelukt. Controleer je invoer en verbinding en probeer opnieuw. Je wijzigingen staan nog in dit scherm.";
}

export async function loadWorkspace(): Promise<Workspace> {
  const client = getSupabase();
  if (!client) throw new Error("De verbinding met de database is nog niet ingesteld.");
  const { data, error } = await client.rpc("get_workspace");
  if (error || !data) throw new Error("Je profiel kon niet worden geladen. Controleer je verificatie en de database-inrichting en probeer opnieuw.");
  const profile = storedProfileSchema.parse(data.profile);
  profile.cpv_codes = profile.cpv_codes.map(normalizeCpvSelection);
  return { ...data, profile } as Workspace;
}

export async function saveWorkspace(profile: Profile, revision: number, complete = false): Promise<Workspace> {
  const valid = profileSchema.safeParse(profile);
  if (!valid.success) throw new Error(valid.error.issues.map(i => i.message).join(" · "));
  if (complete) { const errors = validateCompletion(profile); if (errors.length) throw new Error(errors.join(" ")); }
  const client = getSupabase();
  if (!client) throw new Error("De databaseverbinding ontbreekt.");
  const { data: catalog, error: catalogError } = await client.rpc("get_cpv_catalog_info");
  if (catalogError || catalog?.source_sha256 !== cpvMetadata.source_sha256)
    throw new Error("De bijgewerkte CPV-catalogus is nog niet geactiveerd. Neem contact op met de beheerder. Je bestaande gegevens blijven bewaard; nieuwe wijzigingen zijn nog niet opgeslagen.");
  const payload = { ...valid.data, cpv_codes: valid.data.cpv_codes.map(normalizeCpvSelection) };
  const { data, error } = await client.rpc("save_onboarding", { payload, complete, expected_revision: revision });
  if (error) throw new Error(friendlyError(error));
  return { ...data, profile: profileSchema.parse(data.profile) } as Workspace;
}
