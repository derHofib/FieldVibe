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
      <h1 className="text-lg font-bold text-label">Dauer-Aufträge</h1>
      <p className="text-sm text-label2">
        Wiederkehrende Aufträge im Überblick -- die daraus erzeugten Vorgänge erscheinen zusätzlich
        ganz normal im Feed.
      </p>

      {isLoading ? (
        <p className="text-center text-label2">Lädt…</p>
      ) : !dauerauftraege || dauerauftraege.length === 0 ? (
        <p className="text-sm text-label2">Noch keine Dauer-Aufträge angelegt.</p>
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
            >
              <div>
                <div className="text-sm font-medium text-label">
                  {d.titel}
                  {d.anzahl_ziele > 1 && (
                    <span className="ml-2 border border-sep px-2 py-0.5 text-xs font-normal text-label">
                      {d.anzahl_ziele} Anlagen
                    </span>
                  )}
                </div>
                <div className="text-xs text-label2">
                  {kundeNameById.get(d.kunde_id) ?? "–"} · alle {d.intervall_tage} Tage
                  {d.naechste_faelligkeit_am && ` · nächste Fälligkeit ${d.naechste_faelligkeit_am}`}
                </div>
              </div>
              {!d.aktiv && (
                <span className="border border-sep px-2 py-1 text-xs text-label">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => navigate("/dauerauftraege/neu")}
        className="btn-touch w-full rounded-md btn-ap-primary py-2 font-medium"
      >
        + Neuer Dauer-Auftrag
      </button>
    </div>
  );
}
