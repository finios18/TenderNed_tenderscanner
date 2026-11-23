import { PGlite } from "@electric-sql/pglite";
import { readFile } from "node:fs/promises";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Workspace } from "../src/lib/validation/profile";
import { scannerExport } from "../src/lib/export/config";
import { cpvMetadata } from "../src/lib/cpv";
const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";
let db: PGlite;
async function asUser(id: string) {
  await db.exec("reset role");
  await db.query("select set_config('request.jwt.claim.sub',$1,false)", [id]);
  await db.exec("set role authenticated");
}
async function workspace() { return (await db.query<{ w: Workspace }>("select public.get_workspace() w")).rows[0].w; }
async function save(w: Workspace) {
  return (await db.query<{ w: Workspace }>("select public.save_onboarding($1::jsonb,false,$2) w", [JSON.stringify(w.profile), w.revision])).rows[0].w;
}
beforeAll(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create schema auth;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema auth,public to anon,authenticated,service_role; grant execute on function auth.uid() to anon,authenticated,service_role;`);
  await db.exec(await readFile(new URL("../supabase/migrations/202611190001_initial.sql", import.meta.url), "utf8"));
  await db.query("insert into auth.users values($1,'a@example.com',now()),($2,'b@example.com',now())", [A, B]);
  await db.query("update public.companies set company_name='Bestaand bedrijf' where owner_user_id=$1", [A]);
  await db.query(`insert into public.cpv_codes(search_profile_id,cpv_code,description)
    select s.id,code,description from public.search_profiles s join public.companies c on c.id=s.company_id,
    (values('72000000','Eigen bewaarde omschrijving'),('99999999','Oude onbekende selectie')) items(code,description) where c.owner_user_id=$1`, [A]);
  await db.exec(await readFile(new URL("../supabase/migrations/202611190002_cpv_catalog.sql", import.meta.url), "utf8"));
  await db.exec(await readFile(new URL("../supabase/migrations/202611190003_cpv_selection.sql", import.meta.url), "utf8"));
  await db.exec(await readFile(new URL("../supabase/migrations/202611230001_simplify_profile.sql", import.meta.url), "utf8"));
}, 60000);
afterAll(async () => { await db?.close(); });

describe.sequential("CPV-upgrade, opslag en autorisatie", () => {
  it("behoudt bestaande data en onbekende oude selecties zonder ze stil te verwijderen", async () => {
    await asUser(A); const w = await workspace();
    expect(w.profile.company.company_name).toBe("Bestaand bedrijf");
    expect(w.profile.cpv_codes).toHaveLength(2);
    expect(w.profile.cpv_codes.find(c => c.code === "72000000-5")).toMatchObject({ include_descendants: false, original_description: "Eigen bewaarde omschrijving" });
    expect(w.profile.cpv_codes.some(c => c.code === "99999999")).toBe(true);
    expect(w.revision).toBe(1); expect(w.subscription.trial_started_at).toBeNull();
  });
  it("weigert onbekende codes, fout controlecijfer en duplicaten ook rechtstreeks via de RPC", async () => {
    await asUser(A); const w = await workspace();
    await expect(save(w)).rejects.toThrow(/officiële CPV/);
    w.profile.cpv_codes = [{code:"72000000-6",description:"Fout"}];
    await expect(save(w)).rejects.toThrow(/officiële CPV/);
    w.profile.cpv_codes = [{code:"72000000",description:"IT"},{code:"72000000-5",description:"IT"}];
    await expect(save(w)).rejects.toThrow(/duplicate key/i);
    expect((await workspace()).revision).toBe(1);
    expect((await workspace()).profile.cpv_codes).toHaveLength(2);
  });
  it("bewaart exact/subtree expliciet en laadt dezelfde selectie na een nieuwe sessie", async () => {
    await asUser(A); const w = await workspace();
    w.profile.cpv_codes = w.profile.cpv_codes.filter(c => c.code === "72000000-5").map(c => ({...c, include_descendants:true}));
    const saved = await save(w);
    expect(saved.profile.cpv_codes[0].include_descendants).toBe(true);
    await asUser(B); expect((await workspace()).profile.cpv_codes).toEqual([]);
    await asUser(A); expect((await workspace()).profile.cpv_codes).toEqual(saved.profile.cpv_codes);
    const oldClient = await workspace(); delete oldClient.profile.cpv_codes[0].include_descendants;
    expect((await save(oldClient)).profile.cpv_codes[0].include_descendants).toBe(true);
    const changed = await workspace(); changed.profile.cpv_codes[0].include_descendants = false;
    expect((await save(changed)).profile.cpv_codes[0].include_descendants).toBe(false);
  });
  it("maakt de catalogus alleen-lezen en blokkeert toegang tot oude interne RPC’s", async () => {
    await asUser(A);
    expect((await db.query<{count:number}>("select count(*)::int count from public.cpv_catalog")).rows[0].count).toBe(9454);
    await expect(db.exec("delete from public.cpv_catalog")).rejects.toThrow(/permission denied/i);
    await expect(db.exec("update public.cpv_catalog set description_nl='vervalst'")).rejects.toThrow(/permission denied/i);
    await expect(db.exec("select public.save_onboarding_v1('{}'::jsonb,false,0)")).rejects.toThrow(/permission denied/i);
    await expect(db.exec("select public.workspace_for_company_v1('00000000-0000-4000-8000-000000000000')")).rejects.toThrow(/permission denied/i);
    const info = (await db.query<{info:{source_sha256:string}}>("select public.get_cpv_catalog_info() info")).rows[0].info;
    expect(info.source_sha256).toBe(cpvMetadata.source_sha256);
    await db.exec("reset role; set role anon");
    await expect(db.exec("select * from public.cpv_catalog")).rejects.toThrow(/permission denied/i);
  });
  it("exporteert subtree en overlap in SQL identiek aan de TypeScript-export", async () => {
    await asUser(A); const w = await workspace();
    w.profile.cpv_codes[0].include_descendants = true;
    w.profile.cpv_codes.push({code:"72300000",description:"Eigen data-omschrijving",include_descendants:false});
    const saved = await save(w); await db.exec("reset role");
    const config = (await db.query<{config:ReturnType<typeof scannerExport>}>("select public.admin_export_config($1) config", [saved.company_id])).rows[0].config;
    expect(config).toEqual(scannerExport(saved));
    expect(config.scanner_config.cpv_whitelist).toContain("72300000");
    expect(config.scanner_config.cpv_whitelist).not.toContain("79620000");
    expect(new Set(config.scanner_config.cpv_whitelist).size).toBe(config.scanner_config.cpv_whitelist.length);
    await asUser(A); await expect(db.query("select public.admin_export_config($1)", [saved.company_id])).rejects.toThrow(/permission denied/i);
  });
});
