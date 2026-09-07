import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";

export function FormularePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formularOffen, setFormularOffen] = useState(false);
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: formulare, isLoading } = useQuery({
    queryKey: ["formulare"],
    queryFn: () => formulareApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: () => formulareApi.create({ name: name.trim(), beschreibung: beschreibung.trim() || undefined }),
    onSuccess: (formular) => {
      queryClient.invalidateQueries({ queryKey: ["formulare"] });
      navigate(`/formulare/${formular.id}`);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Formular konnte nicht angelegt werden"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    if (!name.trim()) {
      setFehler("Bitte einen Namen angeben");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div>
        <h1 className="text-lg font-bold text-ind-ink">Formulare</h1>
        <p className="mt-1 text-sm text-ind-ink-3">
          Eigene Checklisten und Protokolle, die Technikern beim passenden Auftragstyp zum Ausfüllen
          angeboten werden.
        </p>
      </div>

      {formularOffen ? (
        <form
          onSubmit={submit}
          className="space-y-3 border border-ind-line bg-ind-bg p-4"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-2">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. Wartungsprotokoll Heizung"
              autoFocus
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-2">
              Beschreibung (optional)
            </label>
            <input
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              placeholder="Kurze Erklärung, wofür dieses Formular gedacht ist"
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
            />
          </div>
          {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setFormularOffen(false)}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn-touch btn-clay rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen & bearbeiten
            </button>
          </div>
        </form>
      ) : (
        <button
          onClick={() => setFormularOffen(true)}
          className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium"
        >
          <Plus size={16} strokeWidth={2} /> Neues Formular
        </button>
      )}

      {isLoading ? (
        <p className="text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !formulare || formulare.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Formulare angelegt." />
      ) : (
        <div className="space-y-2">
          {formulare.map((f) => (
            <button
              key={f.id}
              onClick={() => navigate(`/formulare/${f.id}`)}
              className="btn-touch flex w-full items-center justify-between border border-ind-line bg-ind-bg p-3 text-left"
            >
              <div>
                <div className="text-sm font-medium text-ind-ink">{f.name}</div>
                <div className="text-xs text-ind-ink-3">
                  {f.felder.length} {f.felder.length === 1 ? "Feld" : "Felder"}
                  {f.zuordnungen.length > 0 &&
                    ` · ${f.zuordnungen.length} ${f.zuordnungen.length === 1 ? "Auftragstyp" : "Auftragstypen"}`}
                </div>
              </div>
              {!f.aktiv && (
                <span className="border border-ind-line px-2 py-1 text-xs text-ind-ink-2">
                  inaktiv
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
