import { test,expect,type Page } from "@playwright/test";
import { emptyProfile,type Workspace } from "../../src/lib/validation/profile";
import { cpvMetadata } from "../../src/lib/cpv";

test("extension-injected body attributes do not cause hydration warnings",async({page,baseURL})=>{
  const errors:string[]=[];
  page.on("console",message=>{if(message.type()==="error"&&/hydrat|server rendered|didn't match/i.test(message.text()))errors.push(message.text());});
  await page.route(`${baseURL}/`,async route=>{
    const response=await route.fetch();
    const html=(await response.text()).replace("<body",'<body data-new-gr-c-s-check-loaded="14.1349.0" data-gr-ext-installed="" monica-id="extension-test" monica-version="9.0.24"');
    await route.fulfill({response,body:html});
  });
  await page.goto("/");
  await expect(page.locator("body")).toHaveAttribute("monica-id","extension-test");
  await page.getByRole("link",{name:"Start gratis proefperiode"}).first().click();
  await expect(page.getByRole("heading",{name:"Start je gratis proefperiode"})).toBeVisible();
  expect(errors).toEqual([]);
});

async function mockAccount(page:Page, signedIn=true){
  const user={id:"11111111-1111-4111-8111-111111111111",aud:"authenticated",role:"authenticated",email:"test@example.com",email_confirmed_at:"2026-11-19T12:00:00Z",app_metadata:{provider:"email",providers:["email"]},user_metadata:{},created_at:"2026-11-19T12:00:00Z"};
  const token=`${Buffer.from(JSON.stringify({alg:"HS256",typ:"JWT"})).toString("base64url")}.${Buffer.from(JSON.stringify({sub:user.id,exp:Math.floor(Date.now()/1000)+3600})).toString("base64url")}.test`;
  const session={access_token:token,refresh_token:"test-refresh",token_type:"bearer",expires_in:3600,expires_at:Math.floor(Date.now()/1000)+3600,user};
  let workspace:Workspace={company_id:"33333333-3333-4333-8333-333333333333",revision:0,updated_at:"2026-11-19T12:00:00Z",onboarding_completed:false,profile:structuredClone(emptyProfile),subscription:{status:"pending",trial_started_at:null,trial_ends_at:null,activated_at:null}};
  workspace.profile.search.notification_email=user.email;
  if(signedIn)await page.addInitScript(session=>localStorage.setItem("sb-poc-auth-token",JSON.stringify(session)),session);
  await page.route("https://poc.supabase.co/**",async route=>{
    const url=new URL(route.request().url());
    if(url.pathname.endsWith("/user"))return route.fulfill({json:user});
    if(url.pathname.endsWith("/token"))return route.fulfill({json:session});
    if(url.pathname.endsWith("/signup"))return route.fulfill({json:{user,session:null}});
    if(url.pathname.endsWith("/get_workspace"))return route.fulfill({json:workspace});
    if(url.pathname.endsWith("/get_cpv_catalog_info"))return route.fulfill({json:cpvMetadata});
    if(url.pathname.endsWith("/save_onboarding")){
      const body=route.request().postDataJSON();
      expect(body.expected_revision).toBe(workspace.revision);
      workspace={...workspace,revision:workspace.revision+1,profile:body.payload,onboarding_completed:workspace.onboarding_completed||body.complete,updated_at:new Date().toISOString(),subscription:{...workspace.subscription,status:body.complete?"submitted":workspace.subscription.status}};
      return route.fulfill({json:workspace});
    }
    return route.fulfill({json:{}});
  });
  return ()=>workspace;
}

test("homepage is responsive, registration is reachable and private routes require login",async({page})=>{
  await page.goto("/");await expect(page.getByRole("heading",{name:/De juiste opdracht/})).toBeVisible();
  await expect(page.locator("#werkwijze .process-steps > li")).toHaveCount(7);
  await expect(page.getByText("Afgevallen op CPV?",{exact:false})).toBeVisible();
  await page.screenshot({path:"test-results/home-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});await expect(page.locator("body")).toHaveJSProperty("scrollWidth",390);
  await page.screenshot({path:"test-results/home-mobile.png",fullPage:true});
  await page.getByRole("link",{name:"Start gratis proefperiode"}).first().click();await expect(page.getByRole("heading",{name:"Start je gratis proefperiode"})).toBeVisible();
  await page.goto("/dashboard/");await expect(page).toHaveURL(/inloggen/);
});

test("registration requests confirmation and login opens the account",async({page})=>{
  await mockAccount(page,false);await page.goto("/registreren/");
  await page.getByLabel("E-mailadres",{exact:true}).fill("test@example.com");await page.getByLabel("Wachtwoord",{exact:true}).fill("een-lang-testwachtwoord");
  await page.getByRole("checkbox").check();await page.getByRole("button",{name:"Account aanmaken"}).click();await expect(page.getByRole("status")).toContainText("verificatiemail");
  await page.goto("/inloggen/");await page.getByLabel("E-mailadres",{exact:true}).fill("test@example.com");await page.getByLabel("Wachtwoord",{exact:true}).fill("een-lang-testwachtwoord");await page.getByRole("button",{name:"Inloggen",exact:true}).click();await expect(page).toHaveURL(/dashboard/);await expect(page.getByRole("heading",{name:"Profiel in voorbereiding"})).toBeVisible();
  await page.getByRole("button",{name:"Uitloggen",exact:true}).click();await expect(page).toHaveURL(/inloggen/);
  await page.getByRole("link",{name:"Wachtwoord vergeten?"}).click();await expect(page.getByRole("heading",{name:"Wachtwoord vergeten?",exact:true})).toBeVisible();await page.getByLabel("E-mailadres",{exact:true}).fill("test@example.com");await page.getByRole("button",{name:"Stuur herstellink"}).click();await expect(page.getByRole("status")).toContainText("herstellink");
});

test("eight-step onboarding saves, edits lists, normalizes history and submits",async({page})=>{
  const read=await mockAccount(page);await page.goto("/onboarding/");
  await page.getByLabel("Bedrijfsnaam",{exact:true}).fill("Fictieve Data BV");await page.getByRole("button",{name:"Bewaar en verder"}).click();
  for(const label of ["Wat zijn jullie belangrijkste specialisaties?","Wat lever je nadrukkelijk niet?","Wat onderscheidt jouw bedrijf?"]) await expect(page.getByLabel(label,{exact:true})).toHaveCount(0);
  await page.getByLabel("Wat doet jouw bedrijf?",{exact:true}).fill("Wij leveren data engineers en analisten.");await page.getByRole("button",{name:"Bewaar en verder"}).click();
  await page.getByRole("button",{name:"Open onderliggende codes van 72000000-5"}).click();
  await expect(page.getByRole("checkbox",{name:/72300000-8/})).toBeVisible();
  await page.getByLabel("Zoek een CPV-code",{exact:true}).fill("72000000");
  await page.getByRole("checkbox",{name:/72000000-5/}).check();
  await expect(page.getByRole("heading",{name:"Geselecteerde CPV-codes (1)"})).toBeVisible();
  await page.getByLabel("Bereik voor 72000000-5",{exact:true}).selectOption("subtree");
  await page.getByRole("button",{name:"Bewaar en verder"}).click();await page.getByLabel("Keywords",{exact:true}).fill("Python, data engineering, Python");await page.getByRole("button",{name:"Toevoegen",exact:true}).first().click();
  await expect(page.getByLabel("Negatieve keywords",{exact:true})).toHaveCount(0);await page.getByRole("button",{name:"Bewaar en verder"}).click();
  await expect(page.getByRole("button",{name:"Publicaties toevoegen",exact:true})).toHaveCount(1);
  await page.getByLabel("Publicaties toevoegen: aan deelgenomen",{exact:true}).fill("123456\nhttps://www.tenderned.nl/aankondigingen/overzicht/123456/publicatie\n234567");await page.getByRole("button",{name:"Publicaties toevoegen",exact:true}).first().click();
  await page.getByLabel("Toelichting bij 123456",{exact:false}).fill("Vergelijkbare opdracht");await page.getByRole("button",{name:"Bewaar en verder"}).click();
  for(const label of ["Gewenste regio’s","Voorkeur voor opdrachtgevers","Certificeringen en vereisten die je bezit"]) await expect(page.getByLabel(label,{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Bewaar en verder"}).click();await page.getByLabel("Ontvangstfrequentie").selectOption("3");await page.getByRole("button",{name:"Bewaar en verder"}).click();
  await page.screenshot({path:"test-results/onboarding-review.png",fullPage:true});await page.getByRole("checkbox").check();await page.getByRole("button",{name:"Aanmelding bevestigen"}).click();
  await expect(page).toHaveURL(/dashboard/);await expect(page.getByRole("heading",{name:"Aanmelding ontvangen"})).toBeVisible();
  expect(read().profile.keywords).toHaveLength(2);expect(read().profile.historical_tenders).toHaveLength(2);expect(read().profile.search.email_frequency_days).toBe(3);expect(read().profile.search.minimum_contract_value).toBeNull();expect(read().profile.cpv_codes[0].include_descendants).toBe(true);
  await page.getByRole("link",{name:"Zoekprofiel wijzigen"}).click();await expect(page.getByLabel("Bedrijfsnaam",{exact:true})).toHaveValue("Fictieve Data BV");
  await page.getByRole("button",{name:/CPV-codes/}).click();await expect(page.getByLabel("Bereik voor 72000000-5",{exact:true})).toHaveValue("subtree");
  await page.getByRole("button",{name:"Verwijder CPV-code 72000000-5"}).click();await page.getByRole("button",{name:"Tussentijds opslaan"}).click();await expect(page.getByRole("status").filter({hasText:"Opgeslagen"})).toBeVisible();expect(read().profile.cpv_codes).toHaveLength(0);
});

test("CPV-selector searches all sectors, distinguishes exact/subtree and works on mobile",async({page})=>{
  const read = await mockAccount(page);await page.setViewportSize({width:390,height:844});
  await page.goto("/onboarding/?stap=3");
  await expect(page.getByRole("heading",{name:"CPV-codes",exact:true})).toBeVisible();
  await expect(page.getByText("9.454 officiële basiscodes.",{exact:false})).toBeVisible();
  await expect(page.getByLabel("Belangrijk bij je CPV-keuze")).toContainText("liever meer mogelijk relevante codes aan dan te weinig");
  await expect(page.getByText("De aanvullende woordenlijst is niet opgenomen.",{exact:false})).toHaveCount(0);
  await page.getByLabel("Zoek een CPV-code",{exact:true}).fill("politieauto");
  await page.getByRole("checkbox",{name:/34114200-1/}).check();
  await expect(page.getByLabel("Bereik voor 34114200-1",{exact:true})).toHaveValue("exact");
  await page.getByLabel("Zoek een CPV-code",{exact:true}).fill("34114000-9");
  await page.getByRole("button",{name:"Selecteer 34114000-9 inclusief onderliggende codes",exact:true}).click();
  await expect(page.getByLabel("Bereik voor 34114000-9",{exact:true})).toHaveValue("subtree");
  await page.getByRole("button",{name:"Selecteer 34114000-9 inclusief onderliggende codes",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Geselecteerde CPV-codes (2)"})).toBeVisible();
  await page.getByLabel("Zoek een CPV-code",{exact:true}).fill("99999999");
  await expect(page.getByText("Geen codes gevonden.",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Tussentijds opslaan"}).click();
  await expect(page.getByRole("status").filter({hasText:"Opgeslagen"})).toBeVisible();
  expect(read().profile.cpv_codes).toHaveLength(2);
  await page.screenshot({path:"test-results/cpv-mobile.png",fullPage:true});
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth",390);
});
