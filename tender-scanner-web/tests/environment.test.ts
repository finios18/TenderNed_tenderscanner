import { spawnSync } from "node:child_process";
import { describe,expect,it } from "vitest";
function validate(key:string,url="https://example.supabase.co") {
  return spawnSync(process.execPath,["scripts/validate-env.mjs"],{cwd:process.cwd(),encoding:"utf8",env:{...process.env,NEXT_PUBLIC_SUPABASE_URL:url,NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:key}});
}
describe("Publieke buildconfiguratie",()=>{
  it("weigert geheime of service-role sleutels voor de browser",()=>{
    expect(validate("sb_secret_fictitious_test_key").status).not.toBe(0);
    const jwt=`test.${Buffer.from(JSON.stringify({role:"service_role"})).toString("base64url")}.test`;
    expect(validate(jwt).status).not.toBe(0);
  });
  it("accepteert publieke configuratie of een onverbonden preview",()=>{
    expect(validate("sb_publishable_fictitious_test_key").status).toBe(0);
    expect(validate("","").status).toBe(0);
  });
});
