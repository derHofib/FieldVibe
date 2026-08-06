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
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />

      {!q && tags && tags.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Tags</h2>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <button
                key={tag.id}
                onClick={() => setQ(`#${tag.label}`)}
                className="btn-touch rounded-full bg-white px-3 py-1.5 text-sm text-slate-600 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
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
                className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{hit.titel}</div>
                  {hit.subtitel && (
                    <div className="text-xs text-slate-400 dark:text-slate-500">{hit.subtitel}</div>
                  )}
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
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
