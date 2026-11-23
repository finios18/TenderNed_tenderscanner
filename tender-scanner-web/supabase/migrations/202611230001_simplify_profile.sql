-- Voer eenmalig uit na 202611190003_cpv_selection.sql.
-- Verwijdert bewust vervallen velden, negatieve keywords en niet-deelgenomen voorbeelden.
-- De hele wijziging is één transactie. Publiceer aansluitend de bijbehorende websiteversie.
begin;
delete from public.keywords where type='negative';
delete from public.historical_tenders where category<>'participated';

create or replace function public.workspace_for_company_v1(cid uuid) returns jsonb language sql stable security definer set search_path = '' as $$
 select jsonb_build_object('company_id',c.id,'revision',s.revision,'updated_at',s.updated_at,'onboarding_completed',s.onboarding_completed,
   'subscription',jsonb_build_object('status',b.status,'trial_started_at',b.trial_started_at,'trial_ends_at',b.trial_ends_at,'activated_at',b.activated_at),
   'profile',jsonb_build_object(
     'company',to_jsonb(c)-array['id','owner_user_id','created_at','updated_at'],
     'search',to_jsonb(s)-array['id','company_id','onboarding_completed','revision','updated_at'],
     'cpv_codes',coalesce((select jsonb_agg(jsonb_build_object('code',v.cpv_code,'description',v.description) order by v.created_at,v.cpv_code) from public.cpv_codes v where v.search_profile_id=s.id),'[]'::jsonb),
     'keywords',coalesce((select jsonb_agg(jsonb_build_object('keyword',k.keyword) order by k.created_at,k.keyword) from public.keywords k where k.search_profile_id=s.id),'[]'::jsonb),
     'historical_tenders',coalesce((select jsonb_agg(jsonb_build_object('publication_id',h.publication_id,'original_input',h.original_input,'notes',h.notes) order by h.created_at,h.publication_id) from public.historical_tenders h where h.search_profile_id=s.id),'[]'::jsonb)
   )) from public.companies c join public.search_profiles s on s.company_id=c.id join public.subscriptions b on b.company_id=c.id where c.id=cid
$$;

create or replace function public.save_onboarding_v1(payload jsonb, complete boolean default false, expected_revision integer default null)
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
  -- Verouderde clients mogen verwijderde velden niet stilzwijgend blijven opslaan.
  if exists(select 1 from jsonb_object_keys(se) k where k not in ('business_description','services_description','sectors','desired_contracts','minimum_contract_value','maximum_contract_value','preferred_contract_types','additional_requirements','cpv_notes','email_notes','email_frequency_days','notification_email')) then raise exception 'Onbekend zoekprofielveld; vernieuw de website'; end if;
  if exists(select 1 from jsonb_array_elements(payload->'keywords') v where jsonb_typeof(v) is distinct from 'object' or (v - 'keyword') <> '{}'::jsonb)
    then raise exception 'Keywords bevatten alleen een zoekterm'; end if;
  if exists(select 1 from jsonb_array_elements(payload->'historical_tenders') v where jsonb_typeof(v) is distinct from 'object' or (v - array['publication_id','original_input','notes']) <> '{}'::jsonb)
    then raise exception 'Eerdere opdrachten bevatten alleen deelnames zonder categorie'; end if;
  if complete and (length(trim(coalesce(co->>'company_name','')))=0 or length(trim(coalesce(se->>'business_description','')))=0 or length(trim(coalesce(se->>'notification_email','')))=0) then raise exception 'Vul bedrijfsnaam, bedrijfsomschrijving en ontvangstadres in'; end if;
  update public.companies set company_name=coalesce(co->>'company_name',''), website=coalesce(co->>'website',''), kvk_number=coalesce(co->>'kvk_number',''),
    contact_person=coalesce(co->>'contact_person',''),contact_email=coalesce(co->>'contact_email',''),phone_number=coalesce(co->>'phone_number',''),city=coalesce(co->>'city',''),company_size=coalesce(co->>'company_size','') where id=cid;
  update public.profiles set full_name=coalesce(co->>'contact_person',''),contact_email=coalesce(co->>'contact_email','') where user_id=auth.uid();
  update public.search_profiles set business_description=coalesce(se->>'business_description',''), services_description=coalesce(se->>'services_description',''),sectors=coalesce(se->>'sectors',''),desired_contracts=coalesce(se->>'desired_contracts',''), minimum_contract_value=(se->>'minimum_contract_value')::numeric, maximum_contract_value=(se->>'maximum_contract_value')::numeric,
    preferred_contract_types=coalesce(se->>'preferred_contract_types',''),
    additional_requirements=coalesce(se->>'additional_requirements',''),cpv_notes=coalesce(se->>'cpv_notes',''),email_notes=coalesce(se->>'email_notes',''),
    email_frequency_days=(se->>'email_frequency_days')::smallint, notification_email=coalesce(se->>'notification_email',''),
    onboarding_completed=onboarding_completed or complete, revision=revision+1 where id=sid;
  delete from public.cpv_codes where search_profile_id=sid;
  insert into public.cpv_codes(search_profile_id,cpv_code,description) select sid,x.code,coalesce(x.description,'') from jsonb_to_recordset(payload->'cpv_codes') as x(code text,description text);
  delete from public.keywords where search_profile_id=sid;
  insert into public.keywords(search_profile_id,keyword) select sid,trim(x.keyword) from jsonb_to_recordset(payload->'keywords') as x(keyword text);
  delete from public.historical_tenders where search_profile_id=sid;
  insert into public.historical_tenders(search_profile_id,publication_id,original_input,notes) select sid,x.publication_id,coalesce(x.original_input,''),coalesce(x.notes,'') from jsonb_to_recordset(payload->'historical_tenders') as x(publication_id text,original_input text,notes text);
  if complete and current_status='pending' then update public.subscriptions set status='submitted' where company_id=cid; end if;
  return public.workspace_for_company(cid);
end $$;

create or replace function public.admin_export_config_v1(customer_id uuid) returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare w jsonb; p jsonb; s jsonb; h jsonb;
begin
  w:=public.workspace_for_company(customer_id);
  if w is null then raise exception 'Bedrijf niet gevonden'; end if;
  p:=w->'profile'; s:=p->'search'; h:=p->'historical_tenders';
  return jsonb_build_object('schema_version',3,'customer_id',customer_id,
    'company',(p->'company') || jsonb_build_object('name',p->'company'->'company_name','description',s->'business_description'),
    'contact',jsonb_build_object('email',coalesce(nullif(s->>'notification_email',''),p->'company'->>'contact_email'),'person',p->'company'->'contact_person'),
    'business_context',jsonb_build_object('description',s->'business_description','services',s->'services_description','sectors',s->'sectors','desired_contracts',s->'desired_contracts'),
    'scanner_config', (s-array['business_description','services_description','sectors','desired_contracts']) || jsonb_build_object(
      'cpv_whitelist',coalesce((select jsonb_agg(split_part(v->>'code','-',1)) from jsonb_array_elements(p->'cpv_codes') v),'[]'::jsonb),
      'cpv_details',p->'cpv_codes','keywords',coalesce((select jsonb_agg(v->'keyword') from jsonb_array_elements(p->'keywords') v ),'[]'::jsonb)),
    'historical_tenders',h,
    'subscription',w->'subscription','onboarding_completed',w->'onboarding_completed','updated_at',w->'updated_at');
end $$;

create or replace function public.admin_export_config(customer_id uuid) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare result jsonb; whitelist jsonb; info jsonb;
begin
  if exists(select 1 from public.cpv_codes c join public.search_profiles s on s.id=c.search_profile_id
    where s.company_id=customer_id and not exists(select 1 from public.cpv_catalog d where d.code=c.cpv_code)) then
    raise exception 'Onbekende bestaande CPV-code: corrigeer de selectie vóór export';
  end if;
  result:=public.admin_export_config_v1(customer_id);
  with recursive expanded(code,walk) as (
    select c.cpv_code,c.include_descendants from public.cpv_codes c join public.search_profiles s on s.id=c.search_profile_id where s.company_id=customer_id
    union
    select child.code,true from public.cpv_catalog child join expanded parent on child.parent_code=parent.code where parent.walk
  )
  select coalesce(jsonb_agg(base_code order by base_code),'[]'::jsonb) into whitelist
    from (select distinct d.base_code from expanded e join public.cpv_catalog d on d.code=e.code) codes;
  info:=public.get_cpv_catalog_info();
  result:=jsonb_set(result,'{schema_version}','3'::jsonb);
  result:=jsonb_set(result,'{scanner_config}',(result->'scanner_config') || jsonb_build_object(
    'cpv_whitelist',whitelist,'cpv_dataset',jsonb_build_object('classification',info->'classification','source_sha256',info->'source_sha256')));
  return result;
end $$;

-- CREATE OR REPLACE bewaart privileges; borg de interne en beheerdergrenzen expliciet.
revoke all on function public.workspace_for_company_v1(uuid),public.save_onboarding_v1(jsonb,boolean,integer),public.admin_export_config_v1(uuid) from public,anon,authenticated,service_role;
revoke all on function public.admin_export_config(uuid) from public,anon,authenticated;
grant execute on function public.admin_export_config(uuid) to service_role;

alter table public.search_profiles
  drop column specializations,
  drop column excluded_services,
  drop column competitive_advantages,
  drop column geographic_preferences,
  drop column preferred_buyers,
  drop column certifications;
alter table public.keywords drop column type;
create unique index keyword_unique on public.keywords(search_profile_id,lower(keyword));
alter table public.historical_tenders drop column category;
alter table public.historical_tenders add constraint historical_tenders_publication_unique unique(search_profile_id,publication_id);
update public.search_profiles set revision=revision+1;
notify pgrst, 'reload schema';
commit;
