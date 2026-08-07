import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { dauerauftraegeApi, kundenApi } from "../../api/endpoints";

export function DauerauftraegePage() {
  const navigate = useNavigate();
  const { data: dauerauftraege, isLoading } = useQuery({
    queryKey: ["dauerauftraege"],
    queryFn: () => dauerauftraegeApi.list(),
  });
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const kundeNameById = new Map((kunden ?? []).map((k) => [k.id, k.name]));

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Dauer-Aufträge</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Wiederkehrende Aufträge im Überblick -- die daraus erzeugten Vorgänge erscheinen zusätzlich
        ganz normal im Feed.
      </p>

      {isLoading ? (
        <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>
      ) : !dauerauftraege || dauerauftraege.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine Dauer-Aufträge angelegt.</p>
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
            >
              <div>
                <div className="text-sm font-medium text-slate-800 dark:text-slate-100">
                  {d.titel}
                  {d.anzahl_ziele > 1 && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                      {d.anzahl_ziele} Anlagen
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 dark:text-slate-500">
                  {kundeNameById.get(d.kunde_id) ?? "–"} · alle {d.intervall_tage} Tage
                  {d.naechste_faelligkeit_am && ` · nächste Fälligkeit ${d.naechste_faelligkeit_am}`}
                </div>
              </div>
              {!d.aktiv && (
                <span className="rounded-full bg-slate-200 px-2 py-1 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => navigate("/dauerauftraege/neu")}
        className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 py-2 font-medium text-white"
      >
        + Neuer Dauer-Auftrag
      </button>
    </div>
  );
}
