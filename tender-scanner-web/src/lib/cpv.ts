import dataset from "../data/cpv-2008-nl.json" with { type: "json" };

export type CpvLevel = "division" | "group" | "class" | "category" | "subcategory";
export type CpvEntry = {
  code: string; base_code: string; description_nl: string;
  level: CpvLevel; precision: number; parent_code: string | null;
};
export type CpvSelection = {
  code: string; description: string; include_descendants?: boolean;
  original_description?: string | null;
};
export const cpvMetadata = dataset.metadata;
export const cpvEntries = dataset.entries as CpvEntry[];
export const cpvLevelLabels: Record<CpvLevel, string> = {
  division: "Divisie", group: "Groep", class: "Klasse", category: "Categorie", subcategory: "Subcategorie",
};
const byCode = new Map(cpvEntries.map(entry => [entry.code, entry]));
const byBase = new Map(cpvEntries.map(entry => [entry.base_code, entry]));
const children = new Map<string | null, CpvEntry[]>();
for (const entry of cpvEntries) {
  const siblings = children.get(entry.parent_code) ?? [];
  siblings.push(entry);
  children.set(entry.parent_code, siblings);
}
export function getCpv(code: string): CpvEntry | undefined {
  const value = code.trim();
  return /^\d{8}$/.test(value) ? byBase.get(value) : byCode.get(value);
}
export function cpvChildren(parent: string | null): readonly CpvEntry[] { return children.get(parent) ?? []; }
export function cpvAncestors(code: string): CpvEntry[] {
  const result: CpvEntry[] = [];
  let current = getCpv(code);
  while (current?.parent_code) {
    current = byCode.get(current.parent_code);
    if (current) result.unshift(current);
  }
  return result;
}
export function cpvDescendants(code: string): CpvEntry[] {
  const current = getCpv(code);
  if (!current) return [];
  const result: CpvEntry[] = [];
  function visit(parent: string) {
    for (const child of cpvChildren(parent)) { result.push(child); visit(child.code); }
  }
  visit(current.code);
  return result;
}
function fold(text: string) { return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("nl-NL"); }
// Eenmalige zoekindex; per zoekopdracht alleen strings vergelijken.
const searchIndex = cpvEntries.map(entry => ({ entry, text: fold(`${entry.code} ${entry.description_nl}`) }));
export function searchCpv(query: string): CpvEntry[] {
  const tokens = fold(query.trim()).split(/\s+/).filter(Boolean);
  if (!tokens.length) return [...cpvChildren(null)];
  return searchIndex.filter(row => tokens.every(token => row.text.includes(token))).map(row => row.entry);
}
export function normalizeCpvSelection(selection: CpvSelection): CpvSelection {
  const entry = getCpv(selection.code);
  if (!entry) return { ...selection, include_descendants: selection.include_descendants ?? false };
  return {
    code: entry.code, description: entry.description_nl,
    include_descendants: selection.include_descendants ?? false,
    original_description: selection.original_description ??
      (selection.description && selection.description !== entry.description_nl ? selection.description : null),
  };
}
export function selectCpv(current: CpvSelection[], code: string, includeDescendants = false): CpvSelection[] {
  const entry = getCpv(code);
  if (!entry) throw new Error("Deze code bestaat niet in de officiële CPV 2008-basiswoordenlijst.");
  const existing = current.findIndex(value => getCpv(value.code)?.code === entry.code);
  const selection = { code: entry.code, description: entry.description_nl, include_descendants: includeDescendants };
  return existing < 0 ? [...current, selection] : current.map((value,index) => index === existing ? { ...value, ...selection } : value);
}
export function removeCpv(current: CpvSelection[], code: string): CpvSelection[] {
  const entry = getCpv(code);
  return current.filter(value => entry ? getCpv(value.code)?.code !== entry.code : value.code !== code);
}
export function expandCpvSelections(selections: CpvSelection[]): string[] {
  const bases = new Set<string>();
  for (const selection of selections) {
    const entry = getCpv(selection.code);
    if (!entry) throw new Error(`Onbekende bestaande CPV-code ${selection.code}. Corrigeer je selectie vóór het exporteren.`);
    bases.add(entry.base_code);
    if (selection.include_descendants) for (const child of cpvDescendants(entry.code)) bases.add(child.base_code);
  }
  return [...bases].sort();
}
