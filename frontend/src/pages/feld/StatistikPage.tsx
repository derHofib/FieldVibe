import { useQuery } from "@tanstack/react-query";
import { Clock, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { zeiterfassungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { ZeiterfassungManuellForm } from "../../components/ZeiterfassungManuellForm";

function montagDerWoche(datum: Date): Date {
  const tag = datum.getDay();
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  const montag = new Date(datum);
  montag.setDate(datum.getDate() + diffZuMontag);
  montag.setHours(0, 0, 0, 0);
  return montag;
}

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function formatDauer(startAt: string, endeAt: string | null): number {
  if (!endeAt) return 0;
  return (new Date(endeAt).getTime() - new Date(startAt).getTime()) / 1000 / 3600;
}

// Muss mit ZEITERFASSUNG_KATEGORIE_LABEL in backend/app/schemas/zeiterfassung.py
// uebereinstimmen ("auftrag" hat bewusst kein Label, siehe Kommentar dort --
// stattdessen zeigt die Zeile die Vorgangsnummer).
const KATEGORIE_LABEL: Record<string, string> = {
  verwaltung: "Verwaltung",
  fahrzeit: "Fahrzeit",
  schulung: "Schulung",
  urlaub: "Urlaub",
  krankheit: "Krankheit",
  sonstiges: "Sonstiges",
};

export function StatistikPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [wocheMontag, setWocheMontag] = useState(() => montagDerWoche(new Date()));
  const [formularOffen, setFormularOffen] = useState(false);

  const { data: statistik, refetch: statistikNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-statistik", currentUser?.id],
    queryFn: () => zeiterfassungApi.statistik(),
  });

  const wocheEnde = new Date(wocheMontag);
  wocheEnde.setDate(wocheMontag.getDate() + 6);

  const {
    data: wochenEintraege,
    refetch: wocheNeuLaden,
  } = useQuery({
    queryKey: ["zeiterfassung-woche", currentUser?.id, toDateInput(wocheMontag)],
    queryFn: () =>
      zeiterfassungApi.listFuerZeitraum({
        techniker_id: currentUser!.id,
        von: toDateInput(wocheMontag),
        bis: toDateInput(wocheEnde),
      }),
  });

  async function exportieren() {
    const blob = await zeiterfassungApi.wochenzettelPdf(toDateInput(wocheMontag));
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  const wochensumme = (wochenEintraege ?? []).reduce(
    (summe, e) => summe + formatDauer(e.start_at, e.ende_at),
    0
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Meine Arbeitszeit</h1>
        <button
          onClick={() => setFormularOffen(true)}
          className="btn-touch btn-clay rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
        >
          + Zeit erfassen
        </button>
      </div>

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

      {statistik && (
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg bg-white p-3 text-center shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.wochenstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. diese Woche</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.monatsstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. dieser Monat</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.jahresstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. dieses Jahr</div>
          </div>
        </div>
      )}

      <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
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
          <span className="text-sm font-medium text-slate-700 dark:text-stone-300">
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
          <div className="space-y-1">
            {wochenEintraege!.map((e) => (
              <button
                key={e.id}
                onClick={() => e.vorgang_id && navigate(`/vorgaenge/${e.vorgang_id}`)}
                disabled={!e.vorgang_id}
                className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm disabled:cursor-default dark:bg-stone-800/60"
              >
                <span className="text-slate-600 dark:text-stone-300">
                  {new Date(e.start_at).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}
                  {" · "}
                  <span className="font-medium">
                    {e.vorgang_id ? "Auftrag" : KATEGORIE_LABEL[e.kategorie] ?? e.kategorie}
                  </span>
                  {e.taetigkeit && ` · ${e.taetigkeit}`}
                  {!e.freigegeben && (
                    <span className="ml-1.5 text-xs text-amber-600 dark:text-amber-400">
                      (offen)
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-medium text-slate-700 dark:text-stone-300">
                  {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))} Std.
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-stone-800">
          <span className="text-sm font-semibold text-slate-700 dark:text-stone-300">
            Wochensumme: {formatStundenAlsHHMM(wochensumme)} Std.
          </span>
          <button
            onClick={exportieren}
            className="btn-touch flex items-center gap-1.5 rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
          >
            <FileText size={15} strokeWidth={2} /> Als PDF exportieren
          </button>
        </div>
      </div>
    </div>
  );
}
