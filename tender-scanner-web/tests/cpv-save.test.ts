import { beforeEach, describe, expect, it, vi } from "vitest";
const client = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("../src/lib/supabase/client", () => ({ getSupabase: () => client }));
import { saveWorkspace } from "../src/lib/supabase/queries";
import { emptyProfile } from "../src/lib/validation/profile";
import { cpvMetadata, normalizeCpvSelection } from "../src/lib/cpv";

beforeEach(() => client.rpc.mockReset());
describe("Geen stille terugval naar exacte CPV-matching", () => {
  it.each([
    { data: null, error: { code: "PGRST202" } },
    { data: { source_sha256: "verouderde-dataset" }, error: null },
  ])("slaat niets op als catalogus of datasetversie niet overeenkomt", async result => {
    client.rpc.mockResolvedValueOnce(result);
    await expect(saveWorkspace(structuredClone(emptyProfile), 0)).rejects.toThrow(/catalogus is nog niet geactiveerd/);
    expect(client.rpc).toHaveBeenCalledTimes(1);
    expect(client.rpc.mock.calls[0][0]).toBe("get_cpv_catalog_info");
  });
  it("verstuurt de canonieke code én de expliciete subtree-keuze na versiecontrole", async () => {
    const profile = structuredClone(emptyProfile);
    profile.cpv_codes = [{ code: "72000000", description: "Mijn tekst", include_descendants: true }];
    const canonical = normalizeCpvSelection(profile.cpv_codes[0]);
    client.rpc.mockResolvedValueOnce({ data: cpvMetadata, error: null });
    client.rpc.mockResolvedValueOnce({ data: { profile: { ...profile, cpv_codes: [canonical] }, revision: 1 }, error: null });
    const result = await saveWorkspace(profile, 0);
    expect(client.rpc.mock.calls[1]).toEqual(["save_onboarding", {
      payload: { ...profile, cpv_codes: [canonical] }, complete: false, expected_revision: 0,
    }]);
    expect(result.profile.cpv_codes[0].include_descendants).toBe(true);
  });
});
