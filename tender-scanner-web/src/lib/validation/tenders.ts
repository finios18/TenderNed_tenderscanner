import { publicationPattern } from "./profile";

export function normalizePublication(input: string): string | null {
  const value = input.trim();
  if (publicationPattern.test(value)) return value;
  try {
    const url = new URL(value);
    if (!["www.tenderned.nl", "tenderned.nl"].includes(url.hostname) || url.protocol !== "https:" || url.username || url.password || url.port) return null;
    const match = url.pathname.match(/^\/aankondigingen\/overzicht\/([1-9]\d{0,11})(?:\/publicatie)?\/?$/);
    return match?.[1] ?? null;
  } catch { return null; }
}

export function parsePublications(input: string, existing: string[] = []) {
  const seen = new Set(existing);
  const values: { publication_id: string; original_input: string }[] = [];
  const invalid: string[] = [];
  for (const token of input.split(/[\s,;]+/).filter(Boolean)) {
    const id = normalizePublication(token);
    if (!id) invalid.push(token);
    else if (!seen.has(id)) { seen.add(id); values.push({ publication_id: id, original_input: token }); }
  }
  return { values, invalid };
}
