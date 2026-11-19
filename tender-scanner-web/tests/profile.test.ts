import { describe,expect,it } from "vitest";
import { emptyProfile,profileSchema,validateCompletion } from "../src/lib/validation/profile";
import { normalizePublication,parsePublications } from "../src/lib/validation/tenders";
import { scannerExport } from "../src/lib/export/config";

describe("Publicatie-ID’s",()=>{
  it("herkent betrouwbare TenderNed-URL’s en bewaart de oorspronkelijke invoer",()=>{
    expect(normalizePublication("https://www.tenderned.nl/aankondigingen/overzicht/123456/publicatie?x=1")).toBe("123456");
    expect(normalizePublication("https://tenderned.nl/aankondigingen/overzicht/123456")).toBe("123456");
    const parsed=parsePublications("123456\t234567\nhttps://www.tenderned.nl/aankondigingen/overzicht/234567/publicatie;345678,rommel",["123456"]);
    expect(parsed.values.map(v=>v.publication_id)).toEqual(["234567","345678"]);
    expect(parsed.invalid).toEqual(["rommel"]);
  });
  it("weigert vreemde hosts, onzekere URL’s en ongeldige ID’s",()=>{
    for(const input of ["0","-123","abc","1234567890123","https://tenderned.nl.evil.com/aankondigingen/overzicht/123456","http://www.tenderned.nl/aankondigingen/overzicht/123456","https://www.tenderned.nl/ander/123456","https://me@www.tenderned.nl/aankondigingen/overzicht/123456"])
      expect(normalizePublication(input),input).toBeNull();
  });
});
describe("Profielvalidatie",()=>{
  it("laat lege concepten en nullable bedragen toe",()=>{expect(profileSchema.safeParse(emptyProfile).success).toBe(true);expect(validateCompletion(emptyProfile)).toHaveLength(3);});
  it("valideert bedragen, frequentie, CPV en dubbele keywords",()=>{
    const p=structuredClone(emptyProfile);p.search.minimum_contract_value=100;p.search.maximum_contract_value=50;expect(profileSchema.safeParse(p).success).toBe(false);
    p.search.maximum_contract_value=null;p.cpv_codes=[{code:"72000000",description:"IT"},{code:"72000000-5",description:"Dubbel"}];expect(profileSchema.safeParse(p).success).toBe(false);
    p.cpv_codes=[];p.keywords=[{keyword:"Python",type:"positive"},{keyword:"python",type:"positive"}];expect(profileSchema.safeParse(p).success).toBe(false);
    p.keywords[1].type="negative";expect(profileSchema.safeParse(p).success).toBe(true);
    expect(profileSchema.safeParse({...p,search:{...p.search,email_frequency_days:5}}).success).toBe(false);
    expect(profileSchema.safeParse({...p,company:{...p.company,website:"javascript:alert(1)"}}).success).toBe(false);
  });
  it("houdt exports stabiel met gescheiden lijsten en volledige bedrijfscontext",()=>{
    const p=structuredClone(emptyProfile);p.company.company_name="Voorbeeld BV";p.search.business_description="Datadiensten";p.search.notification_email="test@example.com";
    p.cpv_codes=[{code:"72000000-5",description:"IT"}];p.keywords=[{keyword:"Python",type:"positive"},{keyword:"Hardware",type:"negative"}];
    p.historical_tenders=[{publication_id:"123456",original_input:"123456",category:"participated",notes:"Vergelijkbaar"}];
    expect(validateCompletion(p)).toEqual([]);
    const result=scannerExport({company_id:"fictief",revision:1,updated_at:"2026-11-19T12:00:00Z",onboarding_completed:true,profile:p,subscription:{status:"submitted",trial_started_at:null,trial_ends_at:null,activated_at:null}});
    expect(result.schema_version).toBe(2);expect(result.scanner_config.cpv_whitelist).toEqual(["72000000"]);expect(result.scanner_config.negative_keywords).toEqual(["Hardware"]);expect(result.historical_tenders.participated[0].notes).toBe("Vergelijkbaar");
  });
});
