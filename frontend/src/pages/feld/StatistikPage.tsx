import { useQuery } from "@tanstack/react-query";
import { Clock, FileText, Users } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ZeiterfassungManuellForm } from "../../components/ZeiterfassungManuellForm";
import { ZeiterfassungTagesliste } from "../../components/ZeiterfassungTagesliste";
import { projekteApi, statistikApi, zeiterfassungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import { montagDerWoche, toDateInput } from "../../utils/zeiterfassung";

/** "offene Vorgaenge je Techniker" als schlichte horizontale Balken statt
 * einer Chart-Bibliothek -- passend zum bisher chart-freien Frontend, ein
 * Balken ist hier ausreichend aussagekraeftig (eine Kennzahl pro Techniker,
 * keine Zeitreihe). */
function TechnikerBalken({ name, anzahl, max }: { name: string; anzahl: number; max: number }) {
  const breite = max > 0 ? Math.max(4, (anzahl / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 truncate text-xs text-label">{name}</span>
      <div className="h-4 flex-1 bg-slate-100 dark:bg-stone-800">
        <div className="h-full bg-cyan-600 dark:bg-cyan-500" style={{ width: `${breite}%` }} />
      </div>
      <span className="w-6 shrink-0 text-right text-xs font-semibold text-label">{anzahl}</span>
    </div>
  );
}

function TeamKennzahlen() {
  const [projektId, setProjektId] = useState("");
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const { data: kennzahlen, isLoading } = useQuery({
    queryKey: ["vorgang-kennzahlen", projektId],
    queryFn: () => statistikApi.vorgangKennzahlen(projektId ? { projekt_id: projektId } : {}),
  });

  const maxOffen = Math.max(1, ...(kennzahlen?.offene_vorgaenge_je_techniker.map((t) => t.anzahl_offen) ?? [1]));

  return (
    <div className="space-y-3 border border-sep bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-bold text-label">
          <Users size={15} strokeWidth={2} /> Team-Kennzahlen
        </h2>
        <select
          value={projektId}
          onChange={(e) => setProjektId(e.target.value)}
          className="border border-sep bg-transparent px-2 py-1 text-xs text-label"
        >
          <option value="">Alle Projekte</option>
          {(projekte ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {isLoading || !kennzahlen ? (
        <p className="py-4 text-center text-sm text-label2">Lädt…</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <div className="border border-sep bg-fill p-3 text-center">
              <div className="text-xl font-bold text-label">{kennzahlen.offene_vorgaenge_gesamt}</div>
              <div className="text-xs text-label2">Offene Vorgänge</div>
            </div>
            <div className="border border-sep bg-fill p-3 text-center">
              <div className="text-xl font-bold text-label">{kennzahlen.abgeschlossene_vorgaenge_zeitraum}</div>
              <div className="text-xs text-label2">Abgeschlossen</div>
            </div>
            <div className="border border-sep bg-fill p-3 text-center">
              <div className="text-xl font-bold text-label">
                {kennzahlen.durchschnittliche_durchlaufzeit_tage !== null
                  ? `${kennzahlen.durchschnittliche_durchlaufzeit_tage} T.`
                  : "—"}
              </div>
              <div className="text-xs text-label2">Ø Durchlaufzeit</div>
            </div>
          </div>

          {kennzahlen.offene_vorgaenge_je_techniker.length > 0 && (
            <div className="space-y-1.5 border-t border-slate-100 pt-2 dark:border-stone-800">
              <p className="text-[11px] font-bold tracking-wide text-label2 uppercase">Offen je Techniker</p>
              {kennzahlen.offene_vorgaenge_je_techniker.map((t) => (
                <TechnikerBalken key={t.techniker_id} name={t.techniker_name} anzahl={t.anzahl_offen} max={maxOffen} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function StatistikPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const [wocheMontag, setWocheMontag] = useState(() => montagDerWoche(new Date()));
  const [formularOffen, setFormularOffen] = useState(false);

  // Zwei unabhaengig schaltbare Mandanten-Module auf einer Seite: "Zeit
  // erfassen" (eigene Arbeitszeit tracken/einsehen) und "Auswertung &
  // Export" (Kennzahlen-Kacheln + PDF-Export) -- historisch beides an
  // "statistik" gekoppelt (siehe docs/BACKLOG.md), jetzt getrennt.
  const kannErfassen = istModulAktiv(currentUser, "zeiterfassung");
  const kannAuswerten = istModulAktiv(currentUser, "statistik");

  const { data: statistik, refetch: statistikNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-statistik", currentUser?.id],
    queryFn: () => zeiterfassungApi.statistik(),
    enabled: kannAuswerten,
  });

  const wocheEnde = new Date(wocheMontag);
  wocheEnde.setDate(wocheMontag.getDate() + 6);

  const { data: wochenEintraege, refetch: wocheNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-woche", currentUser?.id, toDateInput(wocheMontag)],
    queryFn: () =>
      zeiterfassungApi.listFuerZeitraum({
        techniker_id: currentUser!.id,
        von: toDateInput(wocheMontag),
        bis: toDateInput(wocheEnde),
      }),
    enabled: kannErfassen,
  });

  async function exportieren() {
    const blob = await zeiterfassungApi.wochenzettelPdf(toDateInput(wocheMontag));
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  if (!kannErfassen && !kannAuswerten) {
    return <EmptyState icon={Clock} text="Diese Funktion ist für deinen Account nicht freigeschaltet." />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-label">Meine Arbeitszeit</h1>
        {kannErfassen && (
          <button
            onClick={() => setFormularOffen(true)}
            className="btn-touch btn-ap-primary px-3 py-1.5 text-sm"
          >
            + Zeit erfassen
          </button>
        )}
      </div>

      {kannAuswerten && hatRecht("statistik", "sehen") && <TeamKennzahlen />}

      {formularOffen && (
        <ZeiterfassungManuellForm
          onClose={() => setFormularOffen(false)}
          onGespeichert={() => {
            setFormularOffen(false);
            void statistikNeuLaden();
            void wocheNeuLaden();
          }}
        />
      )}

      {kannAuswerten && statistik && (
        <div className="grid grid-cols-3 gap-2">
          <div className="border border-sep bg-card p-3 text-center">
            <div className="text-xl font-bold text-label">
              {formatStundenAlsHHMM(Number(statistik.wochenstunden))}
            </div>
            <div className="text-xs text-label2">Std. diese Woche</div>
          </div>
          <div className="border border-sep bg-card p-3 text-center">
            <div className="text-xl font-bold text-label">
              {formatStundenAlsHHMM(Number(statistik.monatsstunden))}
            </div>
            <div className="text-xs text-label2">Std. dieser Monat</div>
          </div>
          <div className="border border-sep bg-card p-3 text-center">
            <div className="text-xl font-bold text-label">
              {formatStundenAlsHHMM(Number(statistik.jahresstunden))}
            </div>
            <div className="text-xs text-label2">Std. dieses Jahr</div>
          </div>
        </div>
      )}

      {kannErfassen && (
        <div className="border border-sep bg-card p-3">
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => {
                const vorherigeWoche = new Date(wocheMontag);
                vorherigeWoche.setDate(wocheMontag.getDate() - 7);
                setWocheMontag(vorherigeWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              ← Woche
            </button>
            <span className="text-sm font-medium text-label">
              {wocheMontag.toLocaleDateString("de-DE")} – {wocheEnde.toLocaleDateString("de-DE")}
            </span>
            <button
              onClick={() => {
                const naechsteWoche = new Date(wocheMontag);
                naechsteWoche.setDate(wocheMontag.getDate() + 7);
                setWocheMontag(naechsteWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              Woche →
            </button>
          </div>

          {(wochenEintraege ?? []).length === 0 ? (
            <EmptyState icon={Clock} text="Keine Zeiterfassungen in dieser Woche." />
          ) : (
            <ZeiterfassungTagesliste
              eintraege={wochenEintraege!}
              onEintragKlick={(vorgangId) => navigate(`/vorgaenge/${vorgangId}`)}
            />
          )}

          {kannAuswerten && (
            <div className="mt-2 flex items-center justify-end border-t border-slate-100 pt-2 dark:border-stone-800">
              <button
                onClick={exportieren}
                className="btn-touch flex items-center gap-1.5 rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium"
              >
                <FileText size={15} strokeWidth={2} /> Als PDF exportieren
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
