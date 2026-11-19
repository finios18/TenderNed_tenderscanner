import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  cpvAncestors, cpvChildren, cpvDescendants, cpvEntries, cpvMetadata,
  expandCpvSelections, getCpv, normalizeCpvSelection, removeCpv, searchCpv, selectCpv,
} from "../src/lib/cpv";
import { emptyProfile, profileSchema, storedProfileSchema } from "../src/lib/validation/profile";

describe("Volledige officiële CPV 2008-dataset", () => {
  it("bevat de 9.454 unieke basiscodes en 45 divisies uit de vastgelegde bron", () => {
    expect(cpvEntries).toHaveLength(9454);
    expect(new Set(cpvEntries.map(entry => entry.code)).size).toBe(9454);
    expect(new Set(cpvEntries.map(entry => entry.base_code)).size).toBe(9454);
    expect(cpvChildren(null)).toHaveLength(45);
    const source = readFileSync(new URL("../data/cpv/source/pianoo_cpv.xlsx", import.meta.url));
    expect(createHash("sha256").update(source).digest("hex")).toBe(cpvMetadata.source_sha256);
    expect(cpvMetadata.supplementary_included).toBe(false);
    expect(cpvMetadata.supplementary_count).toBe(903);
  });
  it("bewaart controlecijfers, voorloopnullen en Nederlandse omschrijvingen", () => {
    for (const entry of cpvEntries) {
      expect(entry.code).toMatch(/^\d{8}-\d$/);
      expect(entry.base_code).toBe(entry.code.slice(0, 8));
      expect(entry.description_nl.trim().length).toBeGreaterThan(0);
    }
    expect(getCpv("03115110-4")?.description_nl).toBe("Katoen");
    expect(getCpv("34114200-1")?.description_nl).toBe("Politieauto's");
    expect(getCpv("72000000")?.code).toBe("72000000-5");
    expect(getCpv("72000000-6")).toBeUndefined();
    expect(getCpv("99999999")).toBeUndefined();
  });
  it("vormt een volledige acyclische boom met bestaande, minder specifieke ouders", () => {
    const seen = new Set<string>();
    function walk(parent: string | null) {
      for (const entry of cpvChildren(parent)) {
        expect(seen.has(entry.code)).toBe(false); seen.add(entry.code);
        expect(entry.parent_code).toBe(parent);
        if (parent) expect(getCpv(parent)!.precision).toBeLessThan(entry.precision);
        walk(entry.code);
      }
    }
    walk(null); expect(seen.size).toBe(9454);
    expect(getCpv("34114200-1")?.parent_code).toBe("34114000-9");
    expect(cpvAncestors("03115110-4").map(entry => entry.base_code)).toEqual(["03000000","03100000","03110000","03115000","03115100"]);
  });
});
describe("Zoeken, selecties en exacte scannersemantiek", () => {
  it("zoekt op volledige code, basiscode, Nederlandse tekst en meerdere woorden", () => {
    expect(searchCpv("72000000-5").map(entry => entry.code)).toEqual(["72000000-5"]);
    expect(searchCpv("politieauto").some(entry => entry.code === "34114200-1")).toBe(true);
    expect(searchCpv("IT ondersteuning").some(entry => entry.code === "72000000-5")).toBe(true);
    expect(searchCpv("GEEN-BESTAANDE-CODE-OF-OMSCHRIJVING")).toEqual([]);
    expect(searchCpv("")).toHaveLength(45);
  });
  it("selecteert, wijzigt het bereik en verwijdert zonder dubbele codes", () => {
    let selections = selectCpv([], "72000000");
    expect(selections[0].include_descendants).toBe(false);
    selections = selectCpv(selections, "72000000-5", true);
    expect(selections).toHaveLength(1); expect(selections[0].include_descendants).toBe(true);
    expect(removeCpv(selections, "72000000")).toEqual([]);
    expect(() => selectCpv([], "72000000-6")).toThrow(/officiële/);
  });
  it("exporteert exact één code of expliciet de hele subtree, zonder prefixveronderstelling", () => {
    const exact = selectCpv([], "72000000");
    expect(expandCpvSelections(exact)).toEqual(["72000000"]);
    const tree = selectCpv(exact, "72000000", true);
    const bases = expandCpvSelections(tree);
    expect(bases).toContain("72000000"); expect(bases).toContain("72200000"); expect(bases).toContain("72300000");
    expect(bases).not.toContain("79620000");
    expect(bases).toHaveLength(cpvDescendants("72000000").length + 1);
    expect(expandCpvSelections(selectCpv(tree, "72300000"))).toEqual(bases);
  });
  it("behoudt legacy-omschrijvingen en weigert onbekende codes bij nieuwe opslag", () => {
    expect(normalizeCpvSelection({ code:"72000000",description:"Mijn omschrijving" })).toMatchObject({code:"72000000-5",original_description:"Mijn omschrijving",include_descendants:false});
    const old = {...structuredClone(emptyProfile),cpv_codes:[{code:"99999999",description:"Oud"}]};
    expect(storedProfileSchema.safeParse(old).success).toBe(true);
    expect(profileSchema.safeParse(old).success).toBe(false);
    expect(() => expandCpvSelections(old.cpv_codes)).toThrow(/Onbekende/);
  });
});
