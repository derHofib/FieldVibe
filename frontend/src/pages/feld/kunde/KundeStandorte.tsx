import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { standorteApi } from "../../../api/endpoints";
import { ApiError } from "../../../api/client";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { EmptyState } from "../../../components/EmptyState";

function NeuerStandort({ kundeId }: { kundeId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [strasse, setStrasse] = useState("");
  const [plz, setPlz] = useState("");
  const [ort, setOrt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [bezeichnungFehler, setBezeichnungFehler] = useState<string | null>(null);

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      standorteApi.create({
        kunde_id: kundeId,
        bezeichnung,
        adresse:
          strasse || plz || ort
            ? { strasse: strasse || undefined, plz: plz || undefined, ort: ort || undefined }
            : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] });
      setZeigen(false);
      setBezeichnung("");
      setStrasse("");
      setPlz("");
      setOrt("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Standort konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setBezeichnungFehler("Bitte eine Bezeichnung eingeben.");
      return;
    }
    setBezeichnungFehler(null);
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neuer Standort
      </button>
      <AnlegenPanel offen={zeigen} titel="Neuer Standort" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <Feld label="Bezeichnung" pflicht fehler={bezeichnungFehler}>
            {(p) => (
              <input
                {...p}
                autoFocus
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
                placeholder="z.B. Filiale Nord"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <Feld label="Straße und Hausnummer">
            {(p) => <input {...p} value={strasse} onChange={(e) => setStrasse(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <div className="grid grid-cols-2 gap-3">
            <Feld label="PLZ">{(p) => <input {...p} value={plz} onChange={(e) => setPlz(e.target.value)} className={FELD_KLASSE} />}</Feld>
            <Feld label="Ort">{(p) => <input {...p} value={ort} onChange={(e) => setOrt(e.target.value)} className={FELD_KLASSE} />}</Feld>
          </div>
          {error && (
            <p role="alert" className="text-fliess text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sekundaer font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

export function StandorteVerwaltung({ kundeId, kannVerwalten }: { kundeId: string; kannVerwalten: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: standorte } = useQuery({
    queryKey: ["standorte", kundeId],
    queryFn: () => standorteApi.list(kundeId),
  });

  const toggleAktivMutation = useMutation({
    mutationFn: ({ id, aktiv }: { id: string; aktiv: boolean }) => standorteApi.update(id, { aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] }),
  });

  return (
    <div>
      <h2 className="mb-2 text-fliess font-semibold text-label2">Standorte</h2>
      {!standorte || standorte.length === 0 ? (
        <EmptyState icon={MapPin} text="Keine Standorte." className="py-4" />
      ) : (
        <div className="space-y-2">
          {standorte.map((s) => (
            <div
              key={s.id}
              className={`flex items-center justify-between card-ap p-3 ${
                s.aktiv ? "" : "opacity-60"
              }`}
            >
              <button
                onClick={() => navigate(`/standorte/${s.id}`)}
                className="btn-touch flex-1 text-left"
              >
                <div className="text-fliess font-medium text-label hover:underline">
                  {s.bezeichnung}
                </div>
                {s.adresse?.ort && (
                  <div className="text-sekundaer text-label2">
                    {[s.adresse.strasse, [s.adresse.plz, s.adresse.ort].filter(Boolean).join(" ")]
                      .filter(Boolean)
                      .join(", ")}
                  </div>
                )}
              </button>
              {kannVerwalten && (
                <button
                  onClick={() => toggleAktivMutation.mutate({ id: s.id, aktiv: !s.aktiv })}
                  className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-sekundaer font-semibold"
                >
                  {s.aktiv ? "Deaktivieren" : "Aktivieren"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {kannVerwalten && (
        <div className="mt-2">
          <NeuerStandort kundeId={kundeId} />
        </div>
      )}
    </div>
  );
}
