import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { useState, type FormEvent } from "react";

import { kundenportalApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import type { Leistungstyp, VorgangAnfrageStatus } from "../../types";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Select } from "../../components/apple/Select";

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const STATUS_LABEL: Record<VorgangAnfrageStatus, string> = {
  offen: "In Prüfung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const STATUS_BADGE: Record<VorgangAnfrageStatus, string> = {
  offen: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
  angenommen: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  abgelehnt: "border rounded-[var(--radius-ap-pill)] border-sep text-label2 ",
};

function NeueAnfrage() {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [standortId, setStandortId] = useState("");
  const [anlageId, setAnlageId] = useState("");
  const [zeigeNeuerStandort, setZeigeNeuerStandort] = useState(false);
  const [neuerStandortName, setNeuerStandortName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [titelFehler, setTitelFehler] = useState<string | null>(null);
  const [standortFehler, setStandortFehler] = useState<string | null>(null);

  const { data: standorte } = useQuery({
    queryKey: ["portal-standorte"],
    queryFn: kundenportalApi.standorte,
    enabled: zeigen,
  });
  const { data: anlagen } = useQuery({
    queryKey: ["portal-anlagen"],
    queryFn: kundenportalApi.anlagen,
    enabled: zeigen,
  });
  const anlagenFuerStandort = (anlagen ?? []).filter((a) => !standortId || a.standort_id === standortId);

  const neuerStandortMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => kundenportalApi.standortAnlegen({ bezeichnung: neuerStandortName }),
    onSuccess: (standort) => {
      queryClient.invalidateQueries({ queryKey: ["portal-standorte"] });
      setStandortId(standort.id);
      setZeigeNeuerStandort(false);
      setNeuerStandortName("");
    },
  });

  const createMutation = useMutation({
    meta: { erfolg: "Anfrage gesendet" },
    mutationFn: () =>
      kundenportalApi.anfrageAnlegen({
        titel,
        beschreibung: beschreibung || undefined,
        leistungstyp,
        standort_id: standortId || undefined,
        anlage_id: anlageId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-anfragen"] });
      setZeigen(false);
      setTitel("");
      setBeschreibung("");
      setStandortId("");
      setAnlageId("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anfrage konnte nicht gesendet werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!titel.trim()) {
      setTitelFehler("Bitte einen Titel eingeben.");
      return;
    }
    setTitelFehler(null);
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className="btn-touch btn-ap-primary w-full rounded-lg py-3 text-sm font-medium">
        + Neue Anfrage
      </button>
      <AnlegenPanel offen={zeigen} titel="Neue Anfrage" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <p className="text-xs text-label2">
            Ihre Anfrage wird von uns geprüft und in einen Auftrag übernommen, sobald sie bestätigt ist.
          </p>
          <div>
            <label htmlFor="portal-anfrage-titel" className="mb-1 block text-sm font-medium text-label">
              Titel <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input
              id="portal-anfrage-titel"
              autoFocus
              value={titel}
              onChange={(e) => setTitel(e.target.value)}
              aria-invalid={!!titelFehler}
              aria-describedby={titelFehler ? "portal-anfrage-titel-fehler" : undefined}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
            {titelFehler && (
              <p id="portal-anfrage-titel-fehler" role="alert" className="mt-1 text-xs text-st-fehlt">
                {titelFehler}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="portal-anfrage-beschreibung" className="mb-1 block text-sm font-medium text-label">
              Beschreibung
            </label>
            <textarea
              id="portal-anfrage-beschreibung"
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={3}
              className="w-full resize-none border rounded-[var(--radius-ap-input)] border-sep bg-transparent p-2 text-label"
            />
          </div>
          <div>
            <label htmlFor="portal-anfrage-art" className="mb-1 block text-sm font-medium text-label">
              Art
            </label>
            <Select
              id="portal-anfrage-art"
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </Select>
          </div>

          {(standorte ?? []).length > 0 && (
            <div>
              <label htmlFor="portal-anfrage-standort" className="mb-1 block text-sm font-medium text-label">
                Standort (optional)
              </label>
              <Select
                id="portal-anfrage-standort"
                value={standortId}
                onChange={(e) => {
                  setStandortId(e.target.value);
                  setAnlageId("");
                }}
              >
                <option value="">Kein Standort</option>
                {standorte?.filter((s) => s.aktiv).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.bezeichnung}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {!zeigeNeuerStandort ? (
            <button
              type="button"
              onClick={() => setZeigeNeuerStandort(true)}
              className="btn-touch btn-ap px-4 py-2 text-sm font-medium"
            >
              + Neuer Standort
            </button>
          ) : (
            <div>
              <label htmlFor="portal-anfrage-neuer-standort" className="mb-1 block text-sm font-medium text-label">
                Neuer Standort <span aria-hidden="true" className="text-st-fehlt">*</span>
              </label>
              <div className="flex gap-2">
                <input
                  id="portal-anfrage-neuer-standort"
                  value={neuerStandortName}
                  onChange={(e) => setNeuerStandortName(e.target.value)}
                  placeholder="z.B. Filiale Nord"
                  aria-invalid={!!standortFehler}
                  aria-describedby={standortFehler ? "portal-anfrage-standort-fehler" : undefined}
                  className="btn-touch flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-sm text-label"
                />
                <button
                  type="button"
                  disabled={neuerStandortMutation.isPending}
                  onClick={() => {
                    if (!neuerStandortName.trim()) {
                      setStandortFehler("Bitte eine Bezeichnung eingeben.");
                      return;
                    }
                    setStandortFehler(null);
                    neuerStandortMutation.mutate();
                  }}
                  className="btn-touch btn-ap shrink-0 px-4 py-2 text-sm font-medium"
                >
                  Anlegen
                </button>
              </div>
              {standortFehler && (
                <p id="portal-anfrage-standort-fehler" role="alert" className="mt-1 text-xs text-st-fehlt">
                  {standortFehler}
                </p>
              )}
            </div>
          )}

          {anlagenFuerStandort.length > 0 && (
            <div>
              <label htmlFor="portal-anfrage-anlage" className="mb-1 block text-sm font-medium text-label">
                Anlage (optional)
              </label>
              <Select
                id="portal-anfrage-anlage"
                value={anlageId}
                onChange={(e) => setAnlageId(e.target.value)}
              >
                <option value="">Keine Anlage</option>
                {anlagenFuerStandort.filter((a) => a.aktiv).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.bezeichnung}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {error && <p role="alert" className="text-sm text-st-fehlt">{error}</p>}

          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium"
          >
            Anfrage senden
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

export function PortalAnfragenPage() {
  const { data: anfragen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["portal-anfragen"],
    queryFn: kundenportalApi.anfragen,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-label">Ihre Anfragen</h1>
      <NeueAnfrage />

      {isLoading ? (
        <SkeletonList count={3} />
      ) : ladeFehler && !anfragen ? (
        <FehlerZustand fehler={ladeFehler} was="Die Anfragen" onErneut={() => void neuLaden()} />
      ) : !anfragen || anfragen.length === 0 ? (
        <EmptyState icon={MessageSquareText} text="Noch keine Anfragen gestellt." />
      ) : (
        <div className="space-y-2">
          {anfragen.map((a) => (
            <div
              key={a.id}
              className="card-ap p-4"
            >
              <div className="flex items-start justify-between">
                <div className="font-medium text-label">{a.titel}</div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[a.status]}`}>
                  {STATUS_LABEL[a.status]}
                </span>
              </div>
              {a.beschreibung && (
                <p className="mt-1 text-sm text-label2">{a.beschreibung}</p>
              )}
              {a.ablehnungsgrund && (
                <>
                  <p className="mt-1 text-xs text-label2">Grund: {a.ablehnungsgrund}</p>
                  <p className="mt-1 text-xs text-label2">
                    Bei Fragen wenden Sie sich gerne direkt an uns, oder stellen Sie eine neue Anfrage.
                  </p>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
