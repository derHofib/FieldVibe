import { useQuery } from "@tanstack/react-query";
import { SearchX } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { searchApi, tagsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import type { SearchHit } from "../../types";

const KATEGORIE_LABEL: Record<string, string> = {
  kunde: "Kunde",
  anlage: "Anlage",
  vorgang: "Vorgang",
  tag: "Tag",
};

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
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const { data: results, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => searchApi.search(q),
    enabled: q.trim().length > 0,
  });

  return (
    <div className="space-y-4">
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Kunde, Anlage, Vorgangsnummer, #Tag…"
        className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
      />

      {!q && tags && tags.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">Tags</h2>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <button
                key={tag.id}
                onClick={() => setQ(`#${tag.label}`)}
                className="btn-touch rounded-full bg-white px-3 py-1.5 text-sm text-slate-600 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
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
          ) : results && results.treffer.length > 0 ? (
            results.treffer.map((hit) => (
              <button
                key={`${hit.kategorie}-${hit.id}`}
                onClick={() => navigate(hitPath(hit))}
                className="card-interactive btn-touch flex w-full items-center justify-between border border-ind-line bg-ind-bg p-3 text-left"
              >
                <div>
                  <div className="text-sm font-medium text-ind-ink">{hit.titel}</div>
                  {hit.subtitel && (
                    <div className="text-xs text-ind-ink-3">{hit.subtitel}</div>
                  )}
                </div>
                <span className="border border-ind-line px-2 py-0.5 text-xs text-ind-ink-2">
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
