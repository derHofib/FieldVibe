// Verwaltung der mandanteneigenen Plan-Symbol-Bibliothek (Wallbox,
// Leitungsschutzschalter, Zaehler, ...) fuer den Feldtyp "foto_plan" --
// erreichbar von FormSchemasPage.tsx aus, siehe dortigen "Plan-Symbole"-
// Knopf. Die Symbole selbst werden im Editor eines "foto_plan"-Feldes je
// Feld einzeln ausgewaehlt (FormBuilderCanvas.tsx-Inspector), hier nur
// Hochladen/Umbenennen/Loeschen der Bibliothek als Ganzes.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Shapes, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { planSymboleApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import type { PlanSymbol } from "../../types";

const inputClass = "btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink";

function SymbolKarte({
  symbol,
  onUmbenennen,
  onLoeschen,
  umbenennenPending,
}: {
  symbol: PlanSymbol;
  onUmbenennen: (name: string) => void;
  onLoeschen: () => void;
  umbenennenPending: boolean;
}) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [name, setName] = useState(symbol.name);

  return (
    <div className="flex flex-col items-center gap-2 border border-ind-line bg-ind-bg p-3">
      <div className="flex h-16 w-16 items-center justify-center border border-ind-line-2 bg-ind-hover">
        <img src={symbol.url} alt={symbol.name} className="max-h-12 max-w-12 object-contain" />
      </div>
      {bearbeiten ? (
        <div className="flex w-full items-center gap-1">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="min-w-0 flex-1 border border-ind-line bg-transparent px-1.5 py-1 text-xs text-ind-ink"
          />
          <button
            onClick={() => {
              if (name.trim() && name.trim() !== symbol.name) onUmbenennen(name.trim());
              setBearbeiten(false);
            }}
            disabled={umbenennenPending}
            aria-label="Speichern"
            className="shrink-0 text-ind-acc-txt"
          >
            <Pencil size={13} strokeWidth={1.5} />
          </button>
          <button onClick={() => setBearbeiten(false)} aria-label="Abbrechen" className="shrink-0 text-ind-ink-3">
            <X size={13} strokeWidth={1.5} />
          </button>
        </div>
      ) : (
        <button onClick={() => setBearbeiten(true)} className="w-full truncate text-center text-xs font-medium text-ind-ink hover:text-ind-acc-txt">
          {symbol.name}
        </button>
      )}
      <button
        onClick={onLoeschen}
        className="flex items-center gap-1 text-[11px] text-ind-ink-3 hover:text-rose-600"
      >
        <Trash2 size={12} strokeWidth={1.5} /> Löschen
      </button>
    </div>
  );
}

export function PlanSymbolePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [neuerName, setNeuerName] = useState("");
  const [ausgewaehlteDatei, setAusgewaehlteDatei] = useState<File | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: symbole, isLoading } = useQuery({
    queryKey: ["plan-symbole"],
    queryFn: () => planSymboleApi.list(),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["plan-symbole"] });
  }

  const uploadMutation = useMutation({
    mutationFn: () => planSymboleApi.upload(ausgewaehlteDatei!, neuerName.trim(), ausgewaehlteDatei!.name),
    onSuccess: () => {
      setNeuerName("");
      setAusgewaehlteDatei(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      invalidate();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Symbol konnte nicht hochgeladen werden"),
  });
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => planSymboleApi.rename(id, name),
    onSuccess: invalidate,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Symbol konnte nicht umbenannt werden"),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => planSymboleApi.remove(id),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-4">
      <button onClick={() => navigate("/form-schemas")} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div>
        <h1 className="text-lg font-bold text-ind-ink">Plan-Symbole</h1>
        <p className="mt-1 text-sm text-ind-ink-3">
          Eigene Symbol-Bibliothek für den Feldtyp „Foto (Plan)" — z. B. Wallbox, Leitungsschutzschalter, Zähler.
          Beim Anlegen eines solchen Feldes wählt man aus, welche dieser Symbole dort zur Verfügung stehen.
        </p>
      </div>

      <div className="space-y-2 border border-ind-line bg-ind-bg p-4">
        <p className="text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Neues Symbol</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="btn-touch flex flex-1 cursor-pointer items-center justify-center gap-1.5 border border-dashed border-ind-line-2 px-3 py-2 text-sm text-ind-ink-2 hover:bg-ind-hover">
            <Upload size={15} strokeWidth={1.5} />
            {ausgewaehlteDatei ? ausgewaehlteDatei.name : "Bild wählen (PNG/JPEG/WebP/SVG)"}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              className="hidden"
              onChange={(e) => {
                const datei = e.target.files?.[0] ?? null;
                setAusgewaehlteDatei(datei);
                if (datei && !neuerName.trim()) setNeuerName(datei.name.replace(/\.[^.]+$/, ""));
              }}
            />
          </label>
          <input
            value={neuerName}
            onChange={(e) => setNeuerName(e.target.value)}
            placeholder="Name (z. B. Wallbox)"
            className={`${inputClass} sm:w-56`}
          />
          <button
            onClick={() => uploadMutation.mutate()}
            disabled={!ausgewaehlteDatei || !neuerName.trim() || uploadMutation.isPending}
            className="btn-touch flex shrink-0 items-center justify-center gap-1.5 btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            <Plus size={15} strokeWidth={1.5} /> Hochladen
          </button>
        </div>
        {fehler && <p className="text-xs text-red-600 dark:text-red-400">{fehler}</p>}
      </div>

      {isLoading ? (
        <p className="text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !symbole || symbole.length === 0 ? (
        <EmptyState icon={Shapes} text="Noch keine Plan-Symbole angelegt." />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-6">
          {symbole.map((s) => (
            <SymbolKarte
              key={s.id}
              symbol={s}
              umbenennenPending={renameMutation.isPending}
              onUmbenennen={(name) => renameMutation.mutate({ id: s.id, name })}
              onLoeschen={() => deleteMutation.mutate(s.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
