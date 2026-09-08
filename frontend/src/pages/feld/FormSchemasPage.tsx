// Uebersicht der Formular-Modul-v2-Schemas, gegen /api/form-schemas.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";

const STATUS_LABEL: Record<string, string> = { draft: "Entwurf", published: "Veröffentlicht", archived: "Archiviert" };

export function FormSchemasPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formOffen, setFormOffen] = useState(false);
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: schemas, isLoading } = useQuery({
    queryKey: ["form-schemas"],
    queryFn: () => formModulApi.listSchemas(),
  });

  const createMutation = useMutation({
    mutationFn: () => formModulApi.createSchema({ name: name.trim(), beschreibung: beschreibung.trim() || undefined }),
    onSuccess: (schema) => {
      queryClient.invalidateQueries({ queryKey: ["form-schemas"] });
      navigate(`/form-schemas/${schema.id}`);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Schema konnte nicht angelegt werden"),
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
        <h1 className="text-lg font-bold text-ind-ink">Formular-Schemas</h1>
        <p className="mt-1 text-sm text-ind-ink-3">
          Datenerfassung getrennt von Ansicht: ein Schema kann mehrere Views (Erfassung, Zusammenfassung,
          Ausdruck) bedienen.
        </p>
      </div>

      {formOffen ? (
        <form onSubmit={submit} className="space-y-3 border border-ind-line bg-ind-bg p-4">
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
            <label className="mb-1 block text-xs font-medium text-ind-ink-2">Beschreibung (optional)</label>
            <input
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
            />
          </div>
          {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}
          <div className="flex items-center justify-end gap-2">
            <button type="button" onClick={() => setFormOffen(false)} className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300">
              Abbrechen
            </button>
            <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-clay rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
              Anlegen & bearbeiten
            </button>
          </div>
        </form>
      ) : (
        <button onClick={() => setFormOffen(true)} className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium">
          <Plus size={16} strokeWidth={2} /> Neues Schema
        </button>
      )}

      {isLoading ? (
        <p className="text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !schemas || schemas.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Formular-Schemas angelegt." />
      ) : (
        <div className="space-y-2">
          {schemas.map((s) => (
            <button key={s.id} onClick={() => navigate(`/form-schemas/${s.id}`)} className="btn-touch flex w-full items-center justify-between border border-ind-line bg-ind-bg p-3 text-left">
              <div>
                <div className="text-sm font-medium text-ind-ink">{s.name}</div>
                <div className="text-xs text-ind-ink-3">Version {s.version}</div>
              </div>
              <span className="border border-ind-line px-2 py-1 text-xs text-ind-ink-2">{STATUS_LABEL[s.status]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
