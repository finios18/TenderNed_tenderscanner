import { PGlite } from "@electric-sql/pglite";
import { readFile } from "node:fs/promises";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { profileSchema, type Workspace } from "../src/lib/validation/profile";
import { scannerExport } from "../src/lib/export/config";

const user = "11111111-1111-4111-8111-111111111111";
let db: PGlite;
let companyId: string;
async function migration(name: string) {
  await db.exec(await readFile(new URL(`../supabase/migrations/${name}.sql`, import.meta.url), "utf8"));
}
async function workspace() {
  return (await db.query<{ w: Workspace }>("select public.get_workspace() w")).rows[0].w;
}
beforeAll(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create schema auth;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema auth,public to anon,authenticated,service_role; grant execute on function auth.uid() to anon,authenticated,service_role;`);
  await migration("202611190001_initial");
  await migration("202611190002_cpv_catalog");
  await migration("202611190003_cpv_selection");
  await db.query("insert into auth.users values($1,'migration@example.com',now())", [user]);
  await db.exec(`update public.companies set company_name='Bestaand bedrijf';
    update public.search_profiles set business_description='Datadiensten',specializations='Vervallen tekst',notification_email='ontvangst@example.com';
    insert into public.keywords(search_profile_id,keyword,type) select id,'Python','positive' from public.search_profiles;
    insert into public.keywords(search_profile_id,keyword,type) select id,'Hardware','negative' from public.search_profiles;
    insert into public.historical_tenders(search_profile_id,publication_id,category,notes)
      select id,publication_id,category,'Bewaarde toelichting' from public.search_profiles,
      (values('123456','participated'),('234567','interesting'),('345678','not_interesting')) v(publication_id,category);
    insert into public.cpv_codes(search_profile_id,cpv_code,include_descendants) select id,'72000000-5',true from public.search_profiles;`);
  await migration("202611230001_simplify_profile");
  await db.query("select set_config('request.jwt.claim.sub',$1,false)", [user]);
  await db.exec("set role authenticated");
  companyId = (await workspace()).company_id;
}, 60000);
afterAll(async () => { await db?.close(); });

describe.sequential("Bestaand profiel vereenvoudigen", () => {
  it("verwijdert de vervallen kolommen en bewaart de gewenste gegevens", async () => {
    const columns = (await db.query<{ table_name: string; column_name: string }>(
      "select table_name,column_name from information_schema.columns where table_schema='public'"
    )).rows.map(row => `${row.table_name}.${row.column_name}`);
    for (const name of ["specializations", "excluded_services", "competitive_advantages", "geographic_preferences", "preferred_buyers", "certifications"])
      expect(columns).not.toContain(`search_profiles.${name}`);
    expect(columns).not.toContain("keywords.type");
    expect(columns).not.toContain("historical_tenders.category");
    const w = await workspace();
    expect(profileSchema.safeParse(w.profile).success).toBe(true);
    expect(w.profile.company.company_name).toBe("Bestaand bedrijf");
    expect(w.profile.search.business_description).toBe("Datadiensten");
    expect(w.profile.keywords).toEqual([{ keyword: "Python" }]);
    expect(w.profile.historical_tenders).toEqual([{ publication_id: "123456", original_input: "", notes: "Bewaarde toelichting" }]);
    expect(w.profile.cpv_codes[0].include_descendants).toBe(true);
    expect(w.revision).toBe(1);
  });
  it("weigert oude velden en duplicaten transactioneel, ook bij directe RPC-aanroepen", async () => {
    const w = await workspace();
    for (const profile of [
      { ...w.profile, search: { ...w.profile.search, specializations: "oud" } },
      { ...w.profile, keywords: [{ keyword: "Python", type: "negative" }] },
      { ...w.profile, historical_tenders: [{ ...w.profile.historical_tenders[0], category: "interesting" }] },
      { ...w.profile, keywords: [{ keyword: "Python" }, { keyword: "python" }] },
      { ...w.profile, historical_tenders: [w.profile.historical_tenders[0], w.profile.historical_tenders[0]] },
    ]) {
      await expect(db.query("select public.save_onboarding($1::jsonb,false,$2)", [JSON.stringify(profile), w.revision])).rejects.toThrow();
      expect(await workspace()).toEqual(w);
    }
  });
  it("bewaart toegangsrechten en exporteert de vereenvoudigde structuur identiek", async () => {
    const w = await workspace();
    await expect(db.query("select public.admin_export_config($1)", [companyId])).rejects.toThrow(/permission denied/i);
    await db.exec("reset role; set role service_role");
    const config = (await db.query<{ config: unknown }>("select public.admin_export_config($1) config", [companyId])).rows[0].config;
    expect(config).toEqual(scannerExport(w));
    expect(config).toMatchObject({ schema_version: 3, historical_tenders: w.profile.historical_tenders });
    await expect(db.exec("select public.save_onboarding_v1('{}',false,0)")).rejects.toThrow(/permission denied/i);
  });
});
