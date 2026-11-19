-- Voer na 202611190002_cpv_catalog.sql uit. Bestaande selecties blijven behouden.
begin;
alter table public.cpv_codes add column include_descendants boolean not null default false;
alter table public.cpv_codes add column original_description text check(length(original_description)<=12000);

-- Bekende basiscodes worden canoniek; eerdere eigen omschrijvingen blijven beschikbaar.
update public.cpv_codes c set
  cpv_code=d.code,
  original_description=case when c.description<>d.description_nl and c.description<>'' then c.description else null end,
  description=d.description_nl
from public.cpv_catalog d where c.cpv_code=d.code or c.cpv_code=d.base_code;

-- NOT VALID behoudt eventuele oude onbekende rijen. Nieuwe writes worden wel gecontroleerd.
alter table public.cpv_codes add constraint cpv_catalog_reference
  foreign key(cpv_code) references public.cpv_catalog(code) not valid;

create function public.canonical_cpv_selection() returns trigger language plpgsql security definer set search_path='' as $$
declare official public.cpv_catalog%rowtype;
begin
  select * into official from public.cpv_catalog where code=new.cpv_code or base_code=new.cpv_code;
  if official.code is null then raise exception 'Onbekende CPV 2008-code: %',new.cpv_code using errcode='23503'; end if;
  if new.description<>official.description_nl and new.description<>'' and new.original_description is null then new.original_description:=new.description; end if;
  new.cpv_code:=official.code; new.description:=official.description_nl;
  return new;
end $$;
create trigger cpv_selection_canonical before insert or update of cpv_code,description on public.cpv_codes
  for each row execute function public.canonical_cpv_selection();
revoke all on function public.canonical_cpv_selection() from public,anon,authenticated;

alter function public.workspace_for_company(uuid) rename to workspace_for_company_v1;
create function public.workspace_for_company(cid uuid) returns jsonb language sql stable security definer set search_path='' as $$
  select jsonb_set(public.workspace_for_company_v1(cid),'{profile,cpv_codes}',coalesce((
    select jsonb_agg(jsonb_build_object('code',v.cpv_code,'description',v.description,
      'include_descendants',v.include_descendants,'original_description',v.original_description) order by v.created_at,v.cpv_code)
    from public.cpv_codes v join public.search_profiles s on s.id=v.search_profile_id where s.company_id=cid
  ),'[]'::jsonb))
$$;
revoke all on function public.workspace_for_company(uuid),public.workspace_for_company_v1(uuid) from public,anon,authenticated;

alter function public.save_onboarding(jsonb,boolean,integer) rename to save_onboarding_v1;
revoke all on function public.save_onboarding_v1(jsonb,boolean,integer) from public,anon,authenticated;
create function public.save_onboarding(payload jsonb,complete boolean default false,expected_revision integer default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare normalized jsonb; cid uuid;
begin
  if auth.uid() is null then raise exception 'Log eerst in' using errcode='42501'; end if;
  if payload is null or jsonb_typeof(payload->'cpv_codes') is distinct from 'array' then raise exception 'CPV-selecties ontbreken' using errcode='22023'; end if;
  if exists(select 1 from jsonb_array_elements(payload->'cpv_codes') v
    where jsonb_typeof(v)<>'object' or (v ? 'include_descendants' and jsonb_typeof(v->'include_descendants')<>'boolean')
      or (v ? 'original_description' and jsonb_typeof(v->'original_description') not in ('string','null')))
    then raise exception 'Ongeldig CPV-selectiebereik' using errcode='22023'; end if;
  if exists(select 1 from jsonb_array_elements(payload->'cpv_codes') v
    where not exists(select 1 from public.cpv_catalog d where d.code=v->>'code' or d.base_code=v->>'code'))
    then raise exception 'Een geselecteerde code bestaat niet in de officiële CPV 2008-basiswoordenlijst' using errcode='23503'; end if;
  select id into cid from public.companies where owner_user_id=auth.uid();
  select coalesce(jsonb_agg(jsonb_build_object('code',d.code,'description',d.description_nl,
    'include_descendants',coalesce((v->>'include_descendants')::boolean,previous.include_descendants,false),
    'original_description',coalesce(v->>'original_description',previous.original_description,
      nullif(nullif(v->>'description',''),d.description_nl))) order by d.base_code),'[]'::jsonb)
  into normalized
  from jsonb_array_elements(payload->'cpv_codes') v
  join public.cpv_catalog d on d.code=v->>'code' or d.base_code=v->>'code'
  left join public.search_profiles s on s.company_id=cid
  left join public.cpv_codes previous on previous.search_profile_id=s.id and previous.cpv_code=d.code;

  -- v1 blijft de overige velden valideren en alle writes transactioneel uitvoeren.
  perform public.save_onboarding_v1(jsonb_set(payload,'{cpv_codes}',normalized),complete,expected_revision);
  update public.cpv_codes c set include_descendants=x.include_descendants,original_description=x.original_description
    from jsonb_to_recordset(normalized) x(code text,include_descendants boolean,original_description text),public.search_profiles s
    where c.search_profile_id=s.id and s.company_id=cid and c.cpv_code=x.code;
  return public.workspace_for_company(cid);
end $$;
revoke all on function public.save_onboarding(jsonb,boolean,integer) from public,anon;
grant execute on function public.save_onboarding(jsonb,boolean,integer) to authenticated;

alter function public.admin_export_config(uuid) rename to admin_export_config_v1;
revoke all on function public.admin_export_config_v1(uuid) from public,anon,authenticated,service_role;
create function public.admin_export_config(customer_id uuid) returns jsonb language plpgsql stable security definer set search_path='' as $$
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
  result:=jsonb_set(result,'{schema_version}','2'::jsonb);
  result:=jsonb_set(result,'{scanner_config}',(result->'scanner_config') || jsonb_build_object(
    'cpv_whitelist',whitelist,'cpv_dataset',jsonb_build_object('classification',info->'classification','source_sha256',info->'source_sha256')));
  return result;
end $$;
revoke all on function public.admin_export_config(uuid) from public,anon,authenticated;
grant execute on function public.admin_export_config(uuid) to service_role;
commit;
