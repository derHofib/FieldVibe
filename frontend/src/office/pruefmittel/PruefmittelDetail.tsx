import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { pruefmittelApi } from "../../api/endpoints";
import { Select } from "../../components/apple/Select";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { FELD_KLASSE, Feld } from "../../components/FormularFeld";
import { StatusBadge } from "../../components/StatusBadge";
import type { Pruefmittel, PruefmittelStatus, UserAuswahl } from "../../types";
import { heuteIso } from "../../utils/format";
import {
  FAELLIGKEIT_LABEL,
  FAELLIGKEIT_TONE,
  PRUEFMITTEL_STATUS_LABEL,
  faelligkeitsStufe,
  BALD_FAELLIG_TAGE,
} from "../../utils/pruefmittel";

const datum = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("de-DE") : "–");

function Zeile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-fliess">
      <dt className="text-label2">{label}</dt>
      <dd className="text-right text-label">{children}</dd>
    </div>
  );
}

/** Detailpanel in /pruefmittel/:id: Stammdaten, Kalibrierung eintragen, Bearbeiten, Löschen. */
export function PruefmittelDetail({
  mittel,
  nutzer,
  kannLoeschen,
  onGeloescht,
}: {
  mittel: Pruefmittel;
  nutzer: UserAuswahl[];
  kannLoeschen: boolean;
  onGeloescht: () => void;
}) {
  const queryClient = useQueryClient();
  const bestaetigen = useBestaetigung();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [kalibriertAm, setKalibriertAm] = useState(heuteIso());
  const [form, setForm] = useState({
    bezeichnung: mittel.bezeichnung,
    seriennummer: mittel.seriennummer ?? "",
    zugewiesenAn: mittel.zugewiesen_an ?? "",
    intervall: String(mittel.kalibrierintervall_monate),
    status: mittel.status,
  });

  const aendern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: (body: Parameters<typeof pruefmittelApi.update>[1]) => pruefmittelApi.update(mittel.id, body),
    onSuccess: () => {
      setBearbeiten(false);
      void queryClient.invalidateQueries({ queryKey: ["pruefmittel"] });
    },
  });

  const loeschen = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => pruefmittelApi.remove(mittel.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pruefmittel"] });
      onGeloescht();
    },
  });

  const stufe = faelligkeitsStufe(mittel.naechste_kalibrierung_am, heuteIso(), heuteIso(BALD_FAELLIG_TAGE));
  const nutzerName = nutzer.find((u) => u.id === mittel.zugewiesen_an)?.name ?? "–";

  return (
    <div className="space-y-4 p-4">
      <div>
        <h2 className="text-titel-mobil font-bold text-label">{mittel.bezeichnung}</h2>
        <div className="mt-1 flex flex-wrap gap-2">
          <StatusBadge label={PRUEFMITTEL_STATUS_LABEL[mittel.status]} tone={mittel.status === "aktiv" ? "slate" : "rose"} />
          {mittel.status === "aktiv" && <StatusBadge label={FAELLIGKEIT_LABEL[stufe]} tone={FAELLIGKEIT_TONE[stufe]} />}
        </div>
      </div>

      {bearbeiten ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            aendern.mutate({
              bezeichnung: form.bezeichnung,
              seriennummer: form.seriennummer || null,
              zugewiesen_an: form.zugewiesenAn || null,
              kalibrierintervall_monate: Number(form.intervall),
              status: form.status,
            });
          }}
        >
          <Feld label="Bezeichnung" pflicht>
            {(p) => <input {...p} value={form.bezeichnung} onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="Seriennummer">
            {(p) => <input {...p} value={form.seriennummer} onChange={(e) => setForm({ ...form, seriennummer: e.target.value })} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="Zugewiesen an">
            {(p) => (
              <Select {...p} value={form.zugewiesenAn} onChange={(e) => setForm({ ...form, zugewiesenAn: e.target.value })}>
                <option value="">Niemand</option>
                {nutzer.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
          <Feld label="Kalibrierintervall (Monate)" pflicht>
            {(p) => (
              <input {...p} type="number" min={1} value={form.intervall} onChange={(e) => setForm({ ...form, intervall: e.target.value })} className={FELD_KLASSE} />
            )}
          </Feld>
          <Feld label="Status">
            {(p) => (
              <Select {...p} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as PruefmittelStatus })}>
                {(Object.keys(PRUEFMITTEL_STATUS_LABEL) as PruefmittelStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {PRUEFMITTEL_STATUS_LABEL[s]}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
          <div className="flex gap-2">
            <button type="submit" disabled={!form.bezeichnung.trim() || Number(form.intervall) < 1 || aendern.isPending} className="btn-ap-primary px-4 py-2 disabled:opacity-50">
              Speichern
            </button>
            <button type="button" onClick={() => setBearbeiten(false)} className="btn-ap px-4 py-2">
              Abbrechen
            </button>
          </div>
        </form>
      ) : (
        <>
          <dl className="divide-y-[0.5px] divide-sep">
            <Zeile label="Seriennummer">{mittel.seriennummer ?? "–"}</Zeile>
            <Zeile label="Zugewiesen an">{nutzerName}</Zeile>
            <Zeile label="Intervall">{mittel.kalibrierintervall_monate} Monate</Zeile>
            <Zeile label="Letzte Kalibrierung">{datum(mittel.letzte_kalibrierung_am)}</Zeile>
            <Zeile label="Nächste Kalibrierung">{datum(mittel.naechste_kalibrierung_am)}</Zeile>
          </dl>
          <button type="button" onClick={() => setBearbeiten(true)} className="btn-ap px-4 py-2">
            Bearbeiten
          </button>
        </>
      )}

      <section aria-label="Kalibrierung eintragen" className="space-y-2 rounded-[var(--radius-ap-card)] bg-fill p-3">
        <Feld label="Kalibrierung erfolgt am">
          {(p) => <input {...p} type="date" max={heuteIso()} value={kalibriertAm} onChange={(e) => setKalibriertAm(e.target.value)} className={FELD_KLASSE} />}
        </Feld>
        <button
          type="button"
          disabled={!kalibriertAm || aendern.isPending}
          onClick={() => aendern.mutate({ letzte_kalibrierung_am: kalibriertAm })}
          className="btn-ap-primary px-4 py-2 disabled:opacity-50"
        >
          Kalibrierung eintragen
        </button>
      </section>

      {kannLoeschen && (
        <button
          type="button"
          disabled={loeschen.isPending}
          onClick={async () => {
            if (await bestaetigen({ titel: `Prüfmittel "${mittel.bezeichnung}" löschen?`, bestaetigenLabel: "Löschen" })) {
              loeschen.mutate();
            }
          }}
          className="w-full rounded-md border border-st-fehlt py-2 text-sekundaer font-medium text-st-fehlt disabled:opacity-50"
        >
          Löschen
        </button>
      )}
    </div>
  );
}
