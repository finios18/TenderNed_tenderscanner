begin;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  full_name varchar(250) not null default '', contact_email varchar(320) not null default '',
  deletion_requested_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.companies (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null unique references public.profiles(user_id) on delete cascade,
  company_name varchar(250) not null default '', website varchar(2048) not null default '',
  kvk_number varchar(8) not null default '' check (kvk_number = '' or kvk_number ~ '^[0-9]{8}$'),
  contact_person varchar(250) not null default '', contact_email varchar(320) not null default '',
  phone_number varchar(50) not null default '', city varchar(250) not null default '',
  company_size varchar(20) not null default '' check (company_size in ('','1','2–10','11–50','51–250','251+')),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check (website = '' or website ~ '^https?://[^[:space:]]+$'),
  check (contact_email = '' or contact_email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')
);
create table public.search_profiles (
  id uuid primary key default gen_random_uuid(), company_id uuid not null unique references public.companies(id) on delete cascade,
  business_description varchar(12000) not null default '', services_description varchar(12000) not null default '',
  specializations varchar(12000) not null default '', sectors varchar(12000) not null default '',
  desired_contracts varchar(12000) not null default '', excluded_services varchar(12000) not null default '',
  competitive_advantages varchar(12000) not null default '', geographic_preferences varchar(12000) not null default '',
  minimum_contract_value numeric check (minimum_contract_value between 0 and 1000000000000),
  maximum_contract_value numeric check (maximum_contract_value between 0 and 1000000000000),
  preferred_contract_types varchar(12000) not null default '', preferred_buyers varchar(12000) not null default '',
  certifications varchar(12000) not null default '', additional_requirements varchar(12000) not null default '',
  cpv_notes varchar(12000) not null default '', email_notes varchar(12000) not null default '',
  email_frequency_days smallint not null default 7 check (email_frequency_days in (1,2,3,7,14)),
  notification_email varchar(320) not null default '' check (notification_email = '' or notification_email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
  onboarding_completed boolean not null default false,
  revision integer not null default 0, updated_at timestamptz not null default now(),
  check (minimum_contract_value is null or maximum_contract_value is null or minimum_contract_value <= maximum_contract_value)
);
create table public.cpv_codes (
  id uuid primary key default gen_random_uuid(), search_profile_id uuid not null references public.search_profiles(id) on delete cascade,
  cpv_code varchar(10) not null check (cpv_code ~ '^[0-9]{8}(-[0-9])?$'), description varchar(250) not null default '',
  created_at timestamptz not null default now()
);
create unique index cpv_unique_base on public.cpv_codes(search_profile_id, split_part(cpv_code,'-',1));
create table public.keywords (
  id uuid primary key default gen_random_uuid(), search_profile_id uuid not null references public.search_profiles(id) on delete cascade,
  keyword varchar(150) not null check (length(trim(keyword)) > 0), type text not null check(type in ('positive','negative')),
  created_at timestamptz not null default now()
);
create unique index keyword_unique on public.keywords(search_profile_id,type,lower(keyword));
create table public.historical_tenders (
  id uuid primary key default gen_random_uuid(), search_profile_id uuid not null references public.search_profiles(id) on delete cascade,
  publication_id varchar(12) not null check(publication_id ~ '^[1-9][0-9]{0,11}$'),
  original_input varchar(2048) not null default '', category text not null check(category in ('participated','interesting','not_interesting')),
  notes varchar(4000) not null default '', created_at timestamptz not null default now(),
  unique(search_profile_id,category,publication_id)
);
create table public.subscriptions (
  id uuid primary key default gen_random_uuid(), company_id uuid not null unique references public.companies(id) on delete cascade,
  status text not null default 'pending' check(status in ('pending','submitted','active','expired','disabled')),
  trial_started_at timestamptz, trial_ends_at timestamptz, activated_at timestamptz,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check (trial_ends_at is null or trial_started_at is null or trial_ends_at > trial_started_at),
  check (status <> 'active' or (trial_started_at is not null and trial_ends_at is not null and activated_at is not null))
);

create function public.touch_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end $$;
create trigger profile_updated before update on public.profiles for each row execute function public.touch_updated_at();
create trigger company_updated before update on public.companies for each row execute function public.touch_updated_at();
create trigger search_updated before update on public.search_profiles for each row execute function public.touch_updated_at();
create trigger subscription_updated before update on public.subscriptions for each row execute function public.touch_updated_at();

create function public.handle_new_user() returns trigger language plpgsql security definer set search_path = '' as $$
declare cid uuid;
begin
  insert into public.profiles(user_id,contact_email) values(new.id,coalesce(new.email,''));
  insert into public.companies(owner_user_id,contact_email) values(new.id,coalesce(new.email,'')) returning id into cid;
  insert into public.search_profiles(company_id,notification_email) values(cid,coalesce(new.email,''));
  insert into public.subscriptions(company_id) values(cid);
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.companies enable row level security;
alter table public.search_profiles enable row level security;
alter table public.cpv_codes enable row level security;
alter table public.keywords enable row level security;
alter table public.historical_tenders enable row level security;
alter table public.subscriptions enable row level security;

create policy profile_own on public.profiles for select to authenticated using(user_id = (select auth.uid()));
create policy company_own on public.companies for select to authenticated using(owner_user_id = (select auth.uid()));
create policy search_own on public.search_profiles for select to authenticated using(exists(select 1 from public.companies c where c.id=company_id and c.owner_user_id=(select auth.uid())));
create policy cpv_own on public.cpv_codes for select to authenticated using(exists(select 1 from public.search_profiles s join public.companies c on c.id=s.company_id where s.id=search_profile_id and c.owner_user_id=(select auth.uid())));
create policy keyword_own on public.keywords for select to authenticated using(exists(select 1 from public.search_profiles s join public.companies c on c.id=s.company_id where s.id=search_profile_id and c.owner_user_id=(select auth.uid())));
create policy history_own on public.historical_tenders for select to authenticated using(exists(select 1 from public.search_profiles s join public.companies c on c.id=s.company_id where s.id=search_profile_id and c.owner_user_id=(select auth.uid())));
create policy subscription_own on public.subscriptions for select to authenticated using(exists(select 1 from public.companies c where c.id=company_id and c.owner_user_id=(select auth.uid())));

-- Mutations only through narrowly scoped, ownership-checked transactional RPCs.
-- Even a forged direct REST request cannot change owner, trial dates or status.
revoke all on public.profiles, public.companies, public.search_profiles, public.cpv_codes, public.keywords, public.historical_tenders, public.subscriptions from anon, authenticated;
grant select on public.profiles, public.companies, public.search_profiles, public.cpv_codes, public.keywords, public.historical_tenders, public.subscriptions to authenticated;
grant all on public.profiles, public.companies, public.search_profiles, public.cpv_codes, public.keywords, public.historical_tenders, public.subscriptions to service_role;

create function public.workspace_for_company(cid uuid) returns jsonb language sql stable security definer set search_path = '' as $$
 select jsonb_build_object('company_id',c.id,'revision',s.revision,'updated_at',s.updated_at,'onboarding_completed',s.onboarding_completed,
   'subscription',jsonb_build_object('status',b.status,'trial_started_at',b.trial_started_at,'trial_ends_at',b.trial_ends_at,'activated_at',b.activated_at),
   'profile',jsonb_build_object(
     'company',to_jsonb(c)-array['id','owner_user_id','created_at','updated_at'],
     'search',to_jsonb(s)-array['id','company_id','onboarding_completed','revision','updated_at'],
     'cpv_codes',coalesce((select jsonb_agg(jsonb_build_object('code',v.cpv_code,'description',v.description) order by v.created_at,v.cpv_code) from public.cpv_codes v where v.search_profile_id=s.id),'[]'::jsonb),
     'keywords',coalesce((select jsonb_agg(jsonb_build_object('keyword',k.keyword,'type',k.type) order by k.created_at,k.keyword) from public.keywords k where k.search_profile_id=s.id),'[]'::jsonb),
     'historical_tenders',coalesce((select jsonb_agg(jsonb_build_object('publication_id',h.publication_id,'original_input',h.original_input,'category',h.category,'notes',h.notes) order by h.created_at,h.publication_id) from public.historical_tenders h where h.search_profile_id=s.id),'[]'::jsonb)
   )) from public.companies c join public.search_profiles s on s.company_id=c.id join public.subscriptions b on b.company_id=c.id where c.id=cid
$$;
revoke all on function public.workspace_for_company(uuid) from public, anon, authenticated;

create function public.get_workspace() returns jsonb language sql stable security definer set search_path = '' as $$
 select public.workspace_for_company(c.id) from public.companies c
 where c.owner_user_id=auth.uid() and exists(select 1 from auth.users u where u.id=auth.uid() and u.email_confirmed_at is not null)
$$;
revoke all on function public.get_workspace() from public, anon;
grant execute on function public.get_workspace() to authenticated;

create function public.save_onboarding(payload jsonb, complete boolean default false, expected_revision integer default null)
 returns jsonb language plpgsql security definer set search_path = '' as $$
declare cid uuid; sid uuid; old_revision integer; current_status text; co jsonb; se jsonb;
begin
  if auth.uid() is null or not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'Verifieer eerst je e-mailadres' using errcode='42501';
  end if;
  select c.id,s.id,s.revision,b.status into cid,sid,old_revision,current_status
    from public.companies c join public.search_profiles s on s.company_id=c.id join public.subscriptions b on b.company_id=c.id
    where c.owner_user_id=auth.uid() for update of c,s,b;
  if cid is null then raise exception 'Geen eigen bedrijf gevonden' using errcode='42501'; end if;
  if current_status='disabled' then raise exception 'Account is uitgeschakeld' using errcode='42501'; end if;
  if expected_revision is null or expected_revision <> old_revision then
    raise exception 'Het profiel is elders gewijzigd. Herlaad voordat je opnieuw opslaat.' using errcode='40001';
  end if;
  if payload is null or jsonb_typeof(payload) <> 'object' then raise exception 'Ongeldig profiel'; end if;
  if exists(select 1 from jsonb_object_keys(payload) k where k not in ('company','search','cpv_codes','keywords','historical_tenders')) then raise exception 'Onbekend profielveld'; end if;
  co := payload->'company'; se := payload->'search';
  if jsonb_typeof(co) <> 'object' or jsonb_typeof(se) <> 'object' or co is null or se is null then raise exception 'Bedrijf en zoekprofiel ontbreken'; end if;
  if exists(select 1 from jsonb_object_keys(co) k where k in ('id','owner_user_id','created_at','updated_at')) then raise exception 'Beveiligd veld'; end if;
  if jsonb_typeof(payload->'cpv_codes') <> 'array' or jsonb_typeof(payload->'keywords') <> 'array' or jsonb_typeof(payload->'historical_tenders') <> 'array' then raise exception 'Lijsten ontbreken'; end if;
  if payload->'cpv_codes' is null or payload->'keywords' is null or payload->'historical_tenders' is null then raise exception 'Lijsten ontbreken'; end if;
  if jsonb_array_length(payload->'cpv_codes')>150 or jsonb_array_length(payload->'keywords')>300 or jsonb_array_length(payload->'historical_tenders')>500 then raise exception 'Te veel lijstitems'; end if;
  if complete and (length(trim(coalesce(co->>'company_name','')))=0 or length(trim(coalesce(se->>'business_description','')))=0 or length(trim(coalesce(se->>'notification_email','')))=0) then raise exception 'Vul bedrijfsnaam, bedrijfsomschrijving en ontvangstadres in'; end if;
  update public.companies set company_name=coalesce(co->>'company_name',''), website=coalesce(co->>'website',''), kvk_number=coalesce(co->>'kvk_number',''),
    contact_person=coalesce(co->>'contact_person',''),contact_email=coalesce(co->>'contact_email',''),phone_number=coalesce(co->>'phone_number',''),city=coalesce(co->>'city',''),company_size=coalesce(co->>'company_size','') where id=cid;
  update public.profiles set full_name=coalesce(co->>'contact_person',''),contact_email=coalesce(co->>'contact_email','') where user_id=auth.uid();
  update public.search_profiles set business_description=coalesce(se->>'business_description',''), services_description=coalesce(se->>'services_description',''),
    specializations=coalesce(se->>'specializations',''),sectors=coalesce(se->>'sectors',''),desired_contracts=coalesce(se->>'desired_contracts',''),
    excluded_services=coalesce(se->>'excluded_services',''),competitive_advantages=coalesce(se->>'competitive_advantages',''),
    geographic_preferences=coalesce(se->>'geographic_preferences',''), minimum_contract_value=(se->>'minimum_contract_value')::numeric, maximum_contract_value=(se->>'maximum_contract_value')::numeric,
    preferred_contract_types=coalesce(se->>'preferred_contract_types',''),preferred_buyers=coalesce(se->>'preferred_buyers',''),certifications=coalesce(se->>'certifications',''),
    additional_requirements=coalesce(se->>'additional_requirements',''),cpv_notes=coalesce(se->>'cpv_notes',''),email_notes=coalesce(se->>'email_notes',''),
    email_frequency_days=(se->>'email_frequency_days')::smallint, notification_email=coalesce(se->>'notification_email',''),
    onboarding_completed=onboarding_completed or complete, revision=revision+1 where id=sid;
  delete from public.cpv_codes where search_profile_id=sid;
  insert into public.cpv_codes(search_profile_id,cpv_code,description) select sid,x.code,coalesce(x.description,'') from jsonb_to_recordset(payload->'cpv_codes') as x(code text,description text);
  delete from public.keywords where search_profile_id=sid;
  insert into public.keywords(search_profile_id,keyword,type) select sid,trim(x.keyword),x.type from jsonb_to_recordset(payload->'keywords') as x(keyword text,type text);
  delete from public.historical_tenders where search_profile_id=sid;
  insert into public.historical_tenders(search_profile_id,publication_id,original_input,category,notes) select sid,x.publication_id,coalesce(x.original_input,''),x.category,coalesce(x.notes,'') from jsonb_to_recordset(payload->'historical_tenders') as x(publication_id text,original_input text,category text,notes text);
  if complete and current_status='pending' then update public.subscriptions set status='submitted' where company_id=cid; end if;
  return public.workspace_for_company(cid);
end $$;
revoke all on function public.save_onboarding(jsonb,boolean,integer) from public, anon;
grant execute on function public.save_onboarding(jsonb,boolean,integer) to authenticated;

create function public.request_account_deletion() returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Log eerst in' using errcode='42501'; end if;
  update public.profiles set deletion_requested_at=now() where user_id=auth.uid();
end $$;
revoke all on function public.request_account_deletion() from public, anon;
grant execute on function public.request_account_deletion() to authenticated;

-- Dashboard-only admin export: no PUBLIC, anon or authenticated EXECUTE permission.
create function public.admin_export_config(customer_id uuid) returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare w jsonb; p jsonb; s jsonb; h jsonb;
begin
  w:=public.workspace_for_company(customer_id);
  if w is null then raise exception 'Bedrijf niet gevonden'; end if;
  p:=w->'profile'; s:=p->'search'; h:=p->'historical_tenders';
  return jsonb_build_object('schema_version',1,'customer_id',customer_id,
    'company',(p->'company') || jsonb_build_object('name',p->'company'->'company_name','description',s->'business_description'),
    'contact',jsonb_build_object('email',coalesce(nullif(s->>'notification_email',''),p->'company'->>'contact_email'),'person',p->'company'->'contact_person'),
    'business_context',jsonb_build_object('description',s->'business_description','services',s->'services_description','specializations',s->'specializations','sectors',s->'sectors','desired_contracts',s->'desired_contracts','excluded_services',s->'excluded_services','competitive_advantages',s->'competitive_advantages'),
    'scanner_config', (s-array['business_description','services_description','specializations','sectors','desired_contracts','excluded_services','competitive_advantages']) || jsonb_build_object(
      'cpv_whitelist',coalesce((select jsonb_agg(split_part(v->>'code','-',1)) from jsonb_array_elements(p->'cpv_codes') v),'[]'::jsonb),
      'cpv_details',p->'cpv_codes','keywords',coalesce((select jsonb_agg(v->'keyword') from jsonb_array_elements(p->'keywords') v where v->>'type'='positive'),'[]'::jsonb),
      'negative_keywords',coalesce((select jsonb_agg(v->'keyword') from jsonb_array_elements(p->'keywords') v where v->>'type'='negative'),'[]'::jsonb)),
    'historical_tenders',jsonb_build_object(
      'participated',coalesce((select jsonb_agg(v-'category') from jsonb_array_elements(h) v where v->>'category'='participated'),'[]'::jsonb),
      'interesting',coalesce((select jsonb_agg(v-'category') from jsonb_array_elements(h) v where v->>'category'='interesting'),'[]'::jsonb),
      'not_interesting',coalesce((select jsonb_agg(v-'category') from jsonb_array_elements(h) v where v->>'category'='not_interesting'),'[]'::jsonb)),
    'subscription',w->'subscription','onboarding_completed',w->'onboarding_completed','updated_at',w->'updated_at');
end $$;
revoke all on function public.admin_export_config(uuid) from public, anon, authenticated;
grant execute on function public.admin_export_config(uuid) to service_role;
revoke all on function public.handle_new_user(), public.touch_updated_at() from public, anon, authenticated;
commit;
