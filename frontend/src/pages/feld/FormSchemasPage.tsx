// Uebersicht der Formular-Modul-v2-Schemas, gegen /api/form-schemas.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Plus, Shapes } from "lucide-react";
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
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-label">Formular-Schemas</h1>
          <p className="mt-1 text-sm text-label2">
            Datenerfassung getrennt von Ansicht: ein Schema kann mehrere Views (Erfassung, Zusammenfassung,
            Ausdruck) bedienen.
          </p>
        </div>
        <button
          onClick={() => navigate("/plan-symbole")}
          className="btn-touch flex shrink-0 items-center gap-1.5 btn-ap px-3 py-1.5 text-sm font-medium"
        >
          <Shapes size={15} strokeWidth={1.5} /> Plan-Symbole
        </button>
      </div>

      {formOffen ? (
        <form onSubmit={submit} className="space-y-3 border border-sep bg-card p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-label">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. Wartungsprotokoll Heizung"
              autoFocus
              className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label">Beschreibung (optional)</label>
            <input
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
            />
          </div>
          {fehler && <p className="text-sm text-st-fehlt ">{fehler}</p>}
          <div className="flex items-center justify-end gap-2">
            <button type="button" onClick={() => setFormOffen(false)} className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-label dark:bg-stone-800 ">
              Abbrechen
            </button>
            <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary px-3 py-1.5 text-sm">
              Anlegen & bearbeiten
            </button>
          </div>
        </form>
      ) : (
        <button onClick={() => setFormOffen(true)} className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md btn-ap-primary py-2 text-sm font-medium">
          <Plus size={16} strokeWidth={2} /> Neues Schema
        </button>
      )}

      {isLoading ? (
        <p className="text-center text-sm text-label2">Lädt…</p>
      ) : !schemas || schemas.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Formular-Schemas angelegt." />
      ) : (
        <div className="space-y-2">
          {schemas.map((s) => (
            <button key={s.id} onClick={() => navigate(`/form-schemas/${s.id}`)} className="btn-touch flex w-full items-center justify-between border border-sep bg-card p-3 text-left">
              <div>
                <div className="text-sm font-medium text-label">{s.name}</div>
                <div className="text-xs text-label2">Version {s.version}</div>
              </div>
              <span className="border border-sep px-2 py-1 text-xs text-label">{STATUS_LABEL[s.status]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
