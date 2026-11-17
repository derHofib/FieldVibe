import { useQuery } from "@tanstack/react-query";
import { statusLabel } from "../../config/vorgangDarstellung";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { SearchX } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { searchApi, tagsApi } from "../../api/endpoints";
import { SearchField } from "../../components/apple/SearchField";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import type { SearchHit } from "../../types";

const KATEGORIE_LABEL: Record<string, string> = {
  kunde: "Kunde",
  anlage: "Anlage",
  vorgang: "Vorgang",
  rechnung: "Rechnung",
  tag: "Tag",
};

// Das Backend liefert Status/Typ als Rohwert im Untertitel.
function subtitelLabel(hit: SearchHit): string {
  const text = hit.subtitel ?? "";
  if (hit.kategorie === "vorgang") return statusLabel(text);
  if (hit.kategorie === "rechnung") {
    const [name, status] = text.split(" · ");
    return status ? `${name} · ${(RECHNUNG_STATUS_LABEL as Record<string, string>)[status] ?? status}` : text;
  }
  return text;
}

function hitPath(hit: SearchHit): string {
  switch (hit.kategorie) {
    case "kunde":
      return `/kunden/${hit.id}`;
    case "anlage":
      return `/anlagen/${hit.id}`;
    case "vorgang":
      return `/vorgaenge/${hit.id}`;
    default:
      return "#";
  }
}

export function SearchPage() {
  const [eingabe, setQ] = useState("");
  const q = useDebouncedValue(eingabe);
  const navigate = useNavigate();

  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const { data: results, isFetching, error: suchFehler, refetch: neuSuchen } = useQuery({
    queryKey: ["search", q],
    queryFn: () => searchApi.search(q),
    enabled: q.trim().length > 0,
  });

  return (
    <div className="space-y-4">
      <SearchField
        autoFocus
        groesse="mobil"
        value={eingabe}
        onChange={setQ}
        placeholder="Kunde, Anlage, Vorgangsnummer, #Tag…"
      />

      {!q && tags && tags.length > 0 && (
        <div>
          <h2 className="mb-2 text-fliess font-semibold text-label2">Tags</h2>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <button
                key={tag.id}
                onClick={() => setQ(`#${tag.label}`)}
                className="btn-touch card-ap rounded-full px-3 py-1.5 text-sekundaer text-label"
              >
                #{tag.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {q && (
        <div className="space-y-2">
          {isFetching ? (
            <SkeletonList count={3} />
          ) : suchFehler && !results ? (
            <FehlerZustand fehler={suchFehler} was="Die Suche" onErneut={() => void neuSuchen()} />
          ) : results && results.treffer.length > 0 ? (
            results.treffer.map((hit) => (
              <button
                key={`${hit.kategorie}-${hit.id}`}
                onClick={() => navigate(hitPath(hit))}
                className="card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
              >
                <div>
                  <div className="text-fliess font-medium text-label">{hit.titel}</div>
                  {hit.subtitel && (
                    <div className="text-sekundaer text-label2">{subtitelLabel(hit)}</div>
                  )}
                </div>
                <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta text-label">
                  {KATEGORIE_LABEL[hit.kategorie]}
                </span>
              </button>
            ))
          ) : (
            <EmptyState icon={SearchX} text="Keine Treffer." />
          )}
        </div>
      )}
    </div>
  );
}
