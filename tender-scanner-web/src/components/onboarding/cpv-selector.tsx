"use client";

import { useDeferredValue, useId, useMemo, useState, type CSSProperties } from "react";
import { ChevronDown, ChevronRight, Search, Trash2 } from "lucide-react";
import {
  cpvAncestors, cpvChildren, cpvDescendants, cpvLevelLabels, cpvMetadata,
  getCpv, removeCpv, searchCpv, selectCpv, type CpvEntry, type CpvSelection,
} from "@/lib/cpv";

const PAGE_SIZE = 50;
type Row = { entry: CpvEntry; depth: number };

export function CpvSelector({ value, onChange }: {
  value: CpvSelection[];
  onChange: (value: CpvSelection[]) => void;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);
  const [error, setError] = useState("");
  const rows = useMemo(() => {
    if (deferredQuery.trim()) return searchCpv(deferredQuery).map(entry => ({ entry, depth: 0 }));
    const result: Row[] = [];
    function visit(parent: string | null, depth: number) {
      for (const entry of cpvChildren(parent)) {
        result.push({ entry, depth });
        if (expanded.has(entry.code)) visit(entry.code, depth + 1);
      }
    }
    visit(null, 0);
    return result;
  }, [deferredQuery, expanded]);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = rows.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const selected = new Map(value.map(item => [getCpv(item.code)?.code ?? item.code, item]));

  function choose(entry: CpvEntry, includeDescendants: boolean) {
    if (!selected.has(entry.code) && value.length >= 150) {
      setError("Je kunt maximaal 150 hoofdselecties opslaan. Een selectie inclusief onderliggende codes telt als één hoofdselectie.");
      return;
    }
    onChange(selectCpv(value, entry.code, includeDescendants));
    setError("");
  }
  function toggleBranch(code: string) {
    setExpanded(previous => {
      const next = new Set(previous);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
    setPage(0);
  }
  function reveal(entry: CpvEntry) {
    setQuery(""); setPage(0);
    setExpanded(new Set([...cpvAncestors(entry.code).map(parent => parent.code), entry.code]));
  }

  return <div className="cpv-selector">
    <aside className="notice cpv-guidance" aria-label="Belangrijk bij je CPV-keuze"><strong>Kies je CPV-codes zo compleet mogelijk</strong><p>De CPV-selectie is de eerste inhoudelijke filter. Een aanbesteding zonder overeenkomende CPV-code wordt overgeslagen, ook als de inhoud interessant kan zijn. Zoektermen kunnen dat niet herstellen.</p><p>Vink bij twijfel liever meer mogelijk relevante codes aan dan te weinig. Kies waar passend ook de onderliggende codes. Een ruimere selectie vergroot de kans op extra resultaten; een te smalle selectie kan interessante opdrachten uitsluiten.</p></aside>
    <div className="cpv-intro"><span className="pill green">CPV 2008 · Nederlands</span>
      <p>{cpvMetadata.count.toLocaleString("nl-NL")} officiële basiscodes. Zoek in alle sectoren of open een divisie. Openen selecteert nog niets.</p>
    </div>
    <div className="field"><label htmlFor={`${id}-search`}><span>Zoek een CPV-code</span></label>
      <div className="cpv-search"><Search size={18} aria-hidden="true"/><input id={`${id}-search`} type="search"
        value={query} placeholder="Zoek op CPV-code of omschrijving..."
        onChange={event => { setQuery(event.target.value); setPage(0); }} aria-describedby={`${id}-hint`}/></div>
      <small id={`${id}-hint`}>Zoek bijvoorbeeld op 72000000, politieauto of schoonmaak. Meerdere woorden worden gecombineerd.</small>
    </div>
    <div className="cpv-toolbar"><h3>{deferredQuery.trim() ? "Zoekresultaten" : "Categorieoverzicht"}</h3>
      <span role="status" aria-live="polite">{rows.length} {deferredQuery.trim() ? "resultaten" : "zichtbare codes"}{query !== deferredQuery ? " · zoeken…" : ""}</span>
    </div>
    <div className="cpv-results" aria-busy={query !== deferredQuery}>
      {!rows.length && <p className="cpv-empty">Geen codes gevonden. Probeer een korter woord of een deel van een CPV-code.</p>}
      <ul className="cpv-catalog-list">{visibleRows.map(({ entry, depth }) => {
        const hasChildren = cpvChildren(entry.code).length > 0;
        const ancestors = cpvAncestors(entry.code);
        const isSelected = selected.has(entry.code);
        const covering = ancestors.find(parent => selected.get(parent.code)?.include_descendants);
        return <li className={`cpv-catalog-row ${isSelected ? "is-selected" : ""}`} key={entry.code}
          style={{ "--cpv-depth": Math.min(depth, 5) } as CSSProperties}>
          <div className="cpv-row-main">
            {hasChildren ? <button type="button" className="icon-button cpv-expand" aria-expanded={expanded.has(entry.code) && !query}
              aria-label={`${query ? "Bekijk" : expanded.has(entry.code) ? "Sluit" : "Open"} onderliggende codes van ${entry.code}`}
              onClick={() => query.trim() ? reveal(entry) : toggleBranch(entry.code)}>
              {!query && expanded.has(entry.code) ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}</button> : <span className="cpv-expand-spacer"/>}
            <input id={`${id}-${entry.base_code}`} type="checkbox" checked={isSelected}
              onChange={event => event.target.checked ? choose(entry, false) : onChange(removeCpv(value, entry.code))}/>
            <label htmlFor={`${id}-${entry.base_code}`} className="cpv-row-label">
              <strong>{entry.code}</strong><span>{entry.description_nl}</span>
            </label>
          </div>
          <div className="cpv-row-detail"><small>{cpvLevelLabels[entry.level]}{ancestors.length ? ` · ${ancestors.map(parent => parent.base_code).join(" › ")}` : " · Hoofdniveau"}</small>
            {covering && <small className="cpv-covered">Al gedekt door {covering.code}</small>}
            {hasChildren && <button type="button" className="cpv-subtree" onClick={() => choose(entry, true)}
              aria-label={`Selecteer ${entry.code} inclusief onderliggende codes`}>Inclusief onderliggende codes kiezen</button>}
          </div>
        </li>;
      })}</ul>
    </div>
    {pageCount > 1 && <div className="cpv-pagination" aria-label="CPV-resultaatpagina’s">
      <button type="button" className="button secondary small" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Vorige resultaten</button>
      <span>Pagina {currentPage + 1} van {pageCount}</span>
      <button type="button" className="button secondary small" disabled={currentPage + 1 === pageCount} onClick={() => setPage(currentPage + 1)}>Volgende resultaten</button>
    </div>}
    {error && <div className="notice error" role="alert">{error}</div>}
    <section className="list-editor cpv-selected"><div className="list-editor-head">
      <h3>Geselecteerde CPV-codes ({value.length})</h3><p>Een vinkje kiest alleen die code. Kies hieronder expliciet of onderliggende codes ook moeten meetellen.</p>
    </div><div className="list-body">
      {!value.length && <p className="empty-note">Nog geen codes geselecteerd. Kies hierboven wat bij je bedrijf past.</p>}
      {value.map(item => {
        const entry = getCpv(item.code);
        const descendants = entry ? cpvDescendants(entry.code) : [];
        return <div className="cpv-selected-item" key={item.code}>
          <div className="cpv-selected-title"><div><strong>{entry?.code ?? item.code}</strong><p>{entry?.description_nl ?? item.description}</p></div>
            <button type="button" className="icon-button" aria-label={`Verwijder CPV-code ${entry?.code ?? item.code}`} onClick={() => onChange(removeCpv(value, item.code))}><Trash2 size={17}/></button>
          </div>
          {!entry ? <div className="notice error">Deze bestaande code komt niet voor in CPV 2008. Hij is niet verwijderd. Vervang of verwijder hem voordat je opnieuw opslaat.</div> :
            <label className="cpv-scope"><span>Bereik voor {entry.code}</span><select aria-label={`Bereik voor ${entry.code}`} value={item.include_descendants ? "subtree" : "exact"}
              onChange={event => choose(entry, event.target.value === "subtree")}>
              <option value="exact">Alleen deze code</option>
              <option value="subtree" disabled={!descendants.length}>Inclusief {descendants.length} onderliggende codes</option>
            </select></label>}
          {item.original_description && <small className="cpv-legacy">Eerdere eigen omschrijving bewaard: {item.original_description}</small>}
        </div>;
      })}
    </div></section>
    <p className="cpv-attribution">Bron: <a href={cpvMetadata.source_page} target="_blank" rel="noopener noreferrer">PIANOo</a> · <a href={cpvMetadata.structure_source} target="_blank" rel="noopener noreferrer">TED CPV 2008</a>.</p>
  </div>;
}
