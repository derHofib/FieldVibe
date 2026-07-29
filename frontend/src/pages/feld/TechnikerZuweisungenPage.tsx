import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { technikerZuweisungenApi } from "../../api/endpoints";

export function TechnikerZuweisungenPage() {
  const navigate = useNavigate();
  const { data: uebersicht, isLoading } = useQuery({
    queryKey: ["techniker-zuweisungen"],
    queryFn: technikerZuweisungenApi.uebersicht,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">Techniker-Zuweisungen</h1>
      <p className="text-sm text-slate-500">
        Welcher Techniker betreut welche Kunden. Zuweisen/Ändern geht über das Kunden-Profil.
      </p>

      {isLoading ? (
        <p className="text-center text-slate-500">Lädt…</p>
      ) : !uebersicht || uebersicht.length === 0 ? (
        <p className="text-sm text-slate-400">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-3">
          {uebersicht.map((row) => (
            <div key={row.techniker.id} className="rounded-lg bg-white p-4 shadow-sm">
              <div className="font-semibold text-slate-800">{row.techniker.name}</div>
              <div className="text-xs text-slate-400">{row.techniker.email}</div>
              {row.kunden.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">Kein Kunde zugewiesen.</p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1">
                  {row.kunden.map((k) => (
                    <button
                      key={k.id}
                      onClick={() => navigate(`/kunden/${k.id}`)}
                      className="btn-touch rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                    >
                      {k.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
