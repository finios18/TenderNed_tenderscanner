import { PGlite } from "@electric-sql/pglite";
import { readFile } from "node:fs/promises";
import { afterAll,beforeAll,describe,expect,it } from "vitest";
import { emptyProfile,profileSchema,type Workspace } from "../src/lib/validation/profile";
import { scannerExport } from "../src/lib/export/config";
const A="11111111-1111-4111-8111-111111111111", B="22222222-2222-4222-8222-222222222222";
let db:PGlite;let cidA:string;let cidB:string;
async function asUser(id:string){await db.exec("reset role");await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id]);await db.exec("set role authenticated");}
async function workspace(){const {rows}=await db.query<{w:Workspace}>("select public.get_workspace() w");return rows[0].w;}
async function save(payload:unknown,revision:number,complete=false){return db.query<{w:Workspace}>("select public.save_onboarding($1::jsonb,$2,$3) w",[JSON.stringify(payload),complete,revision]);}
beforeAll(async()=>{
  db=new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create schema auth;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema auth,public to anon,authenticated,service_role; grant execute on function auth.uid() to anon,authenticated,service_role;`);
  await db.exec(await readFile(new URL("../supabase/migrations/202611190001_initial.sql",import.meta.url),"utf8"));
  await db.exec(await readFile(new URL("../supabase/migrations/202611190002_cpv_catalog.sql",import.meta.url),"utf8"));
  await db.exec(await readFile(new URL("../supabase/migrations/202611190003_cpv_selection.sql",import.meta.url),"utf8"));
  await db.query("insert into auth.users values($1,'a@example.com',now()),($2,'b@example.com',now())",[A,B]);
  await asUser(A);cidA=(await workspace()).company_id;await asUser(B);cidB=(await workspace()).company_id;
},60000);
afterAll(async()=>{await db?.close();});
describe.sequential("PostgreSQL: twee gebruikers, RLS en transacties",()=>{
  it("geeft gebruiker A alleen eigen gegevens op alle zeven tabellen",async()=>{
    await asUser(A);
    for(const table of ["profiles","companies","search_profiles","subscriptions"]){const {rows}=await db.query(`select * from public.${table}`);expect(rows).toHaveLength(1);}
    expect((await db.query("select * from public.companies where id=$1",[cidB])).rows).toHaveLength(0);
    await expect(db.query("update public.companies set company_name='Aanval' where id=$1",[cidB])).rejects.toThrow(/permission denied/i);
    await expect(db.query("select public.workspace_for_company($1)",[cidB])).rejects.toThrow(/permission denied/i);
    await expect(db.query("select public.admin_export_config($1)",[cidB])).rejects.toThrow(/permission denied/i);
  });
  it("slaat een compleet profiel atomair op, zonder de proefperiode te activeren",async()=>{
    await asUser(A);const p=structuredClone(emptyProfile);p.company.company_name="Fictieve Data BV";p.search.business_description="Data engineering";p.search.notification_email="a@example.com";
    p.cpv_codes=[{code:"72000000",description:"IT"}];p.keywords=[{keyword:"Python",type:"positive"},{keyword:"Hardware",type:"negative"}];p.historical_tenders=[{publication_id:"123456",original_input:"123456",category:"interesting",notes:"Fictief"}];
    const result=(await save(p,0,true)).rows[0].w;expect(profileSchema.safeParse(result.profile).success).toBe(true);expect(result.revision).toBe(1);expect(result.subscription.status).toBe("submitted");expect(result.subscription.trial_started_at).toBeNull();
    await expect(db.exec("update public.subscriptions set status='active'")).rejects.toThrow(/permission denied/i);
    await asUser(B);for(const table of ["cpv_codes","keywords","historical_tenders"]){expect((await db.query(`select * from public.${table}`)).rows).toHaveLength(0);}
    expect((await workspace()).profile.company.company_name).toBe("");
  });
  it("weigert andermans ID, ongeldige gegevens en verouderde revisies",async()=>{
    await asUser(A);const w=await workspace();
    await expect(save({...w.profile,company:{...w.profile.company,owner_user_id:B}},w.revision)).rejects.toThrow(/Beveiligd veld/);
    await expect(save(w.profile,0)).rejects.toThrow(/elders gewijzigd/);
    await expect(save({...w.profile,search:{...w.profile.search,email_frequency_days:99}},w.revision)).rejects.toThrow();
    expect((await workspace()).revision).toBe(w.revision);
  });
  it("ondersteunt wijzigen en verwijderen van keywords, CPV en publicaties",async()=>{
    await asUser(A);const w=await workspace();w.profile.keywords=[{keyword:"BI",type:"positive"}];w.profile.cpv_codes=[];w.profile.historical_tenders=[];
    const saved=(await save(w.profile,w.revision)).rows[0].w;expect(saved.profile.cpv_codes).toEqual([]);expect(saved.profile.keywords[0].keyword).toBe("BI");expect(saved.onboarding_completed).toBe(true);
  });
  it("exporteert alleen als beheerder, met dezelfde structuur als de app",async()=>{
    await asUser(A);const w=await workspace();await db.exec("reset role");const {rows}=await db.query<{config:unknown}>("select public.admin_export_config($1) config",[cidA]);expect(rows[0].config).toEqual(scannerExport(w));
  });
  it("weigert anonieme toegang en onvoltooide afronding",async()=>{
    await db.exec("reset role; set role anon");await expect(db.exec("select * from public.companies")).rejects.toThrow(/permission denied/i);await expect(db.exec("select public.get_workspace()")).rejects.toThrow(/permission denied/i);
    await asUser(B);await expect(save(emptyProfile,0,true)).rejects.toThrow(/bedrijfsnaam/);
  });
  it("weigert ongeverifieerde gebruikers en laat kindtabellen niet direct aanpassen",async()=>{
    await db.exec("reset role");const id="44444444-4444-4444-8444-444444444444";
    await db.query("insert into auth.users values($1,'unverified@example.com',null)",[id]);
    await asUser(id);expect(await workspace()).toBeNull();await expect(save(emptyProfile,0)).rejects.toThrow(/Verifieer/);
    await asUser(B);for(const table of ["search_profiles","cpv_codes","keywords","historical_tenders","profiles"]){
      await expect(db.query(`delete from public.${table}`)).rejects.toThrow(/permission denied/i);
    }
  });
  it("laat alleen de beheerder activeren, blokkeert disabled-wijzigingen en bewaart verwijderverzoeken",async()=>{
    await db.exec("reset role");await db.query("update public.subscriptions set status='active',trial_started_at=now(),trial_ends_at=now()+interval '14 days',activated_at=now() where company_id=$1",[cidA]);
    await asUser(A);expect((await workspace()).subscription.status).toBe("active");await db.exec("reset role");await db.query("update public.subscriptions set status='disabled' where company_id=$1",[cidA]);
    await asUser(A);const w=await workspace();await expect(save(w.profile,w.revision)).rejects.toThrow(/uitgeschakeld/);await db.exec("select public.request_account_deletion()");
    const {rows}=await db.query<{deletion_requested_at:string|null}>("select deletion_requested_at from public.profiles");expect(rows[0].deletion_requested_at).not.toBeNull();
  });
});
