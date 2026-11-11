import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { anlagenApi, standorteApi } from "../../../api/endpoints";
import { ApiError } from "../../../api/client";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import type { Anlage, Standort } from "../../../types";

export function NeueAnlage({ kundeId, standorte }: { kundeId: string; standorte: Standort[] }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [anlagentyp, setAnlagentyp] = useState("");
  const [standortId, setStandortId] = useState("");
  const [neuerStandortName, setNeuerStandortName] = useState("");
  const [zeigeNeuerStandort, setZeigeNeuerStandort] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bezeichnungFehler, setBezeichnungFehler] = useState<string | null>(null);
  const [standortFehler, setStandortFehler] = useState<string | null>(null);

  const neuerStandortMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => standorteApi.create({ kunde_id: kundeId, bezeichnung: neuerStandortName }),
    onSuccess: (standort) => {
      queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] });
      setStandortId(standort.id);
      setNeuerStandortName("");
      setZeigeNeuerStandort(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Standort konnte nicht angelegt werden"),
  });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      anlagenApi.create({
        kunde_id: kundeId,
        bezeichnung,
        anlagentyp: anlagentyp || undefined,
        standort_id: standortId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setZeigen(false);
      setBezeichnung("");
      setAnlagentyp("");
      setStandortId("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden"),
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
        + Neue Anlage
      </button>
      <AnlegenPanel offen={zeigen} titel="Neue Anlage" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <Feld label="Bezeichnung" pflicht fehler={bezeichnungFehler}>
            {(p) => <input {...p} autoFocus value={bezeichnung} onChange={(e) => setBezeichnung(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="Typ (optional)">
            {(p) => (
              <input
                {...p}
                value={anlagentyp}
                onChange={(e) => setAnlagentyp(e.target.value)}
                placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          {zeigeNeuerStandort ? (
            <Feld label="Neuer Standort" pflicht fehler={standortFehler}>
              {(p) => (
                <div className="flex gap-2">
                  <input
                    {...p}
                    autoFocus
                    value={neuerStandortName}
                    onChange={(e) => setNeuerStandortName(e.target.value)}
                    placeholder="z.B. Filiale Nord"
                    className="btn-touch flex-1 border border-sep bg-transparent px-3 py-2 text-label"
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
                    className="btn-touch btn-ap shrink-0 px-4 text-sm font-medium"
                  >
                    Anlegen
                  </button>
                  <button type="button" onClick={() => setZeigeNeuerStandort(false)} className="btn-touch btn-ap shrink-0 px-4 text-sm font-medium">
                    Abbrechen
                  </button>
                </div>
              )}
            </Feld>
          ) : (
            <Feld label="Standort (optional)">
              {(p) => (
                <div className="space-y-2">
                  <select {...p} value={standortId} onChange={(e) => setStandortId(e.target.value)} className={FELD_KLASSE}>
                    <option value="">Kein Standort</option>
                    {standorte.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.bezeichnung}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setZeigeNeuerStandort(true)} className={NEU_BUTTON_KLASSE}>
                    + Neuer Standort
                  </button>
                </div>
              )}
            </Feld>
          )}
          {error && (
            <p role="alert" className="text-sm text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

export function AnlageAktivToggle({ anlage, kundeId }: { anlage: Anlage; kundeId: string }) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: () => anlagenApi.update(anlage.id, { aktiv: !anlage.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] }),
  });

  return (
    <button
      onClick={() => toggleMutation.mutate()}
      disabled={toggleMutation.isPending}
      className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-xs font-semibold"
    >
      {anlage.aktiv ? "Deaktivieren" : "Aktivieren"}
    </button>
  );
}
