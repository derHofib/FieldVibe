import { useMutation, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { auswertungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { downloadBlob } from "../../utils/download";
import { istModulAktiv } from "../../utils/module";

function ersterTagDesMonats(): string {
  const heute = new Date();
  return new Date(heute.getFullYear(), heute.getMonth(), 1).toISOString().slice(0, 10);
}

export function AuswertungPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");

  const [von, setVon] = useState(ersterTagDesMonats());
  const [bis, setBis] = useState(new Date().toISOString().slice(0, 10));

  const { data: bericht, isFetching, refetch } = useQuery({
    queryKey: ["ust-va", von, bis],
    queryFn: () => auswertungApi.ustVa(von, bis),
    enabled: false,
  });

  const datevMutation = useMutation({
    mutationFn: () => auswertungApi.datevExportCsv(von, bis),
    onSuccess: (blob) => downloadBlob(blob, `DATEV-Export_${von}_${bis}.csv`),
  });

  if (!abrechnungAktiv || !kannSehen) return <Navigate to="/geschaeft" replace />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Auswertung</h1>
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-500 dark:text-stone-400">
            Von
            <input
              type="date"
              value={von}
              onChange={(e) => setVon(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </label>
          <label className="text-xs text-slate-500 dark:text-stone-400">
            Bis
            <input
              type="date"
              value={bis}
              onChange={(e) => setBis(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </label>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="btn-touch mt-3 w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          USt-VA-Bericht laden
        </button>
      </div>

      {bericht && (
        <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">
            Umsatzsteuer (Ausgangsrechnungen)
          </h2>
          {bericht.umsatzsteuer_saetze.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-stone-500">Keine Umsätze im Zeitraum.</p>
          ) : (
            <div className="space-y-1">
              {bericht.umsatzsteuer_saetze.map((z) => (
                <div key={z.satz} className="flex justify-between text-sm">
                  <span className="text-slate-600 dark:text-stone-300">
                    {z.satz}% auf {z.netto} EUR
                  </span>
                  <span className="font-medium text-slate-800 dark:text-stone-100">{z.steuer} EUR</span>
                </div>
              ))}
            </div>
          )}

          <h2 className="mb-2 mt-4 text-sm font-semibold text-slate-500 dark:text-stone-400">
            Vorsteuer (Eingangsrechnungen)
          </h2>
          {bericht.vorsteuer_saetze.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-stone-500">Keine Vorsteuer im Zeitraum.</p>
          ) : (
            <div className="space-y-1">
              {bericht.vorsteuer_saetze.map((z) => (
                <div key={z.satz} className="flex justify-between text-sm">
                  <span className="text-slate-600 dark:text-stone-300">
                    {z.satz}% auf {z.netto} EUR
                  </span>
                  <span className="font-medium text-slate-800 dark:text-stone-100">{z.steuer} EUR</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-sm dark:border-stone-800">
            <div className="flex justify-between text-slate-500 dark:text-stone-400">
              <span>Summe Umsatzsteuer</span>
              <span>{bericht.summe_umsatzsteuer} EUR</span>
            </div>
            <div className="flex justify-between text-slate-500 dark:text-stone-400">
              <span>Summe Vorsteuer</span>
              <span>{bericht.summe_vorsteuer} EUR</span>
            </div>
            <div className="flex justify-between text-base font-bold text-slate-800 dark:text-stone-100">
              <span>{Number(bericht.zahllast) >= 0 ? "Zahllast" : "Vorsteuerüberhang"}</span>
              <span>{bericht.zahllast} EUR</span>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <h2 className="mb-1 text-sm font-semibold text-slate-500 dark:text-stone-400">DATEV-Export</h2>
        <p className="mb-3 text-xs text-slate-400 dark:text-stone-500">
          Buchungsstapel-CSV auf Basis gängiger SKR03-Konten -- vor dem ersten echten Import bitte mit
          dem Steuerberater abstimmen.
        </p>
        <button
          onClick={() => datevMutation.mutate()}
          disabled={datevMutation.isPending}
          className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
        >
          <Download size={15} strokeWidth={2} /> DATEV-Export (CSV)
        </button>
      </div>
    </div>
  );
}
