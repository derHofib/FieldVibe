// Uebersicht der Formular-Modul-v2-Schemas, gegen /api/form-schemas.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Shapes } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi } from "../../api/endpoints";
import { ClaudeMarke } from "../../components/formModul/ClaudeMarke";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { SkeletonList } from "../../components/Skeleton";

const STATUS_LABEL: Record<string, string> = { draft: "Entwurf", published: "Veröffentlicht", archived: "Archiviert" };

export function FormSchemasPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formOffen, setFormOffen] = useState(false);
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: schemas, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["form-schemas"],
    queryFn: () => formModulApi.listSchemas(),
  });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
      <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
        ← Zurück
      </button>

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-titel-mobil font-bold text-label">Formular-Schemas</h1>
          <p className="mt-1 text-sekundaer text-label2">
            Datenerfassung getrennt von Ansicht: ein Schema kann mehrere Views (Erfassung, Zusammenfassung,
            Ausdruck) bedienen.
          </p>
        </div>
        <button
          onClick={() => navigate("/plan-symbole")}
          className="btn-touch flex shrink-0 items-center gap-1.5 btn-ap px-3 py-1.5 text-sekundaer font-medium"
        >
          <Shapes size={15} strokeWidth={1.5} /> Plan-Symbole
        </button>
      </div>

      <button type="button" onClick={() => setFormOffen(true)} className={NEU_BUTTON_KLASSE}>
        + Neues Schema
      </button>

      <AnlegenPanel offen={formOffen} titel="Neues Schema" onClose={() => setFormOffen(false)}>
        <form onSubmit={submit} noValidate className="space-y-3 p-4">
          <Feld label="Name" pflicht fehler={fehler}>
            {(p) => (
              <input
                {...p}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Wartungsprotokoll Heizung"
                autoFocus
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <Feld label="Beschreibung (optional)">
            {(p) => (
              <input {...p} value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} className={FELD_KLASSE} />
            )}
          </Feld>
          <button type="submit" disabled={createMutation.isPending} className={`${NEU_BUTTON_KLASSE} w-full`}>
            Anlegen & bearbeiten
          </button>
        </form>
      </AnlegenPanel>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !schemas ? (
        <FehlerZustand fehler={ladeFehler} was="Die Formulare" onErneut={() => void neuLaden()} />
      ) : !schemas || schemas.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          text="Noch keine Formular-Schemas angelegt. Ein Schema legt fest, welche Daten ein Formular erfasst."
          action={
            <button type="button" onClick={() => setFormOffen(true)} className={NEU_BUTTON_KLASSE}>
              + Neues Schema
            </button>
          }
        />
      ) : (
        <div className="space-y-2">
          {schemas.map((s) => (
            <button key={s.id} onClick={() => navigate(`/form-schemas/${s.id}`)} className="btn-touch flex w-full items-center justify-between card-ap p-3 text-left">
              <div>
                <div className="flex items-center gap-2 text-fliess font-medium text-label">
                  {s.name}
                  {s.erstellt_via === "ki" && <ClaudeMarke klein />}
                </div>
                <div className="text-sekundaer text-label2">Version {s.version}</div>
              </div>
              <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-1 text-sekundaer text-label">{STATUS_LABEL[s.status]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
