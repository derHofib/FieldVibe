import { useQuery } from "@tanstack/react-query";
import { Clock, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ZeiterfassungManuellForm } from "../../components/ZeiterfassungManuellForm";
import { ZeiterfassungTagesliste } from "../../components/ZeiterfassungTagesliste";
import { zeiterfassungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { montagDerWoche, toDateInput } from "../../utils/zeiterfassung";

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

  const { data: wochenEintraege, refetch: wocheNeuLaden } = useQuery({
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Meine Arbeitszeit</h1>
        <button
          onClick={() => setFormularOffen(true)}
          className="btn-touch btn-clay rounded-full bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
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
          <div className="rounded-lg bg-white p-3 text-center shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.wochenstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. diese Woche</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.monatsstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. dieser Monat</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="text-xl font-bold text-slate-800 dark:text-stone-100">
              {formatStundenAlsHHMM(Number(statistik.jahresstunden))}
            </div>
            <div className="text-xs text-slate-500 dark:text-stone-400">Std. dieses Jahr</div>
          </div>
        </div>
      )}

      <div className="rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
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
          <ZeiterfassungTagesliste
            eintraege={wochenEintraege!}
            onEintragKlick={(vorgangId) => navigate(`/vorgaenge/${vorgangId}`)}
          />
        )}

        <div className="mt-2 flex items-center justify-end border-t border-slate-100 pt-2 dark:border-stone-800">
          <button
            onClick={exportieren}
            className="btn-touch flex items-center gap-1.5 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
          >
            <FileText size={15} strokeWidth={2} /> Als PDF exportieren
          </button>
        </div>
      </div>
    </div>
  );
}
