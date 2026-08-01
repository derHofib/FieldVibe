import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { rechteMatrixApi } from "../api/endpoints";
import type { RechteAktion, RechteBereich, RechteRolle } from "../types";

const ROLLEN: RechteRolle[] = ["mitarbeiter", "controller"];
const ROLLE_LABEL: Record<RechteRolle, string> = {
  mitarbeiter: "Mitarbeiter",
  controller: "Controller",
};

const BEREICHE: RechteBereich[] = [
  "vorgaenge",
  "kunden",
  "material",
  "dispo",
  "abrechnung",
  "statistik",
  "mitarbeiterverwaltung",
];
const BEREICH_LABEL: Record<RechteBereich, string> = {
  vorgaenge: "Aufträge",
  kunden: "Kunden & Anlagen",
  material: "Material",
  dispo: "Dispo/Termine",
  abrechnung: "Angebote & Rechnungen",
  statistik: "Statistik & Exporte",
  mitarbeiterverwaltung: "Mitarbeiterliste",
};

export function RechteMatrixPage() {
  const queryClient = useQueryClient();
  const { data: matrix, isLoading } = useQuery({
    queryKey: ["rechte-matrix"],
    queryFn: rechteMatrixApi.get,
  });

  const setMutation = useMutation({
    mutationFn: ({
      rolle,
      bereich,
      aktion,
      erlaubt,
    }: {
      rolle: RechteRolle;
      bereich: RechteBereich;
      aktion: RechteAktion;
      erlaubt: boolean;
    }) => rechteMatrixApi.set(rolle, bereich, aktion, erlaubt),
    onSuccess: (data) => queryClient.setQueryData(["rechte-matrix"], data),
  });

  function istErlaubt(rolle: RechteRolle, bereich: RechteBereich, aktion: RechteAktion): boolean {
    return (
      matrix?.find((e) => e.rolle === rolle && e.bereich === bereich && e.aktion === aktion)
        ?.erlaubt ?? false
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/accounts" className="text-sm font-medium text-blue-700 hover:underline">
          ← Zurück zu Accounts
        </Link>
        <h1 className="mt-2 text-lg font-bold text-slate-800">Rechte für Controller & Mitarbeiter</h1>
        <p className="mt-1 text-sm text-slate-500">
          Legt fest, was diese beiden Account-Typen je Funktionsbereich sehen und bearbeiten dürfen.
          Mandanten-Admin, Disponent und Techniker sind hiervon nicht betroffen.
        </p>
      </div>

      {isLoading ? (
        <p>Lädt…</p>
      ) : (
        ROLLEN.map((rolle) => (
          <section key={rolle} className="rounded-lg bg-white shadow-sm">
            <h2 className="border-b border-slate-100 px-4 py-3 text-base font-semibold text-slate-800">
              {ROLLE_LABEL[rolle]}
            </h2>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-2">Bereich</th>
                  <th className="px-4 py-2 text-center">Sehen</th>
                  <th className="px-4 py-2 text-center">Bearbeiten</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {BEREICHE.map((bereich) => (
                  <tr key={bereich}>
                    <td className="px-4 py-2 font-medium text-slate-700">{BEREICH_LABEL[bereich]}</td>
                    {(["sehen", "bearbeiten"] as const).map((aktion) => (
                      <td key={aktion} className="px-4 py-2 text-center">
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={istErlaubt(rolle, bereich, aktion)}
                          disabled={setMutation.isPending}
                          onChange={(e) =>
                            setMutation.mutate({
                              rolle,
                              bereich,
                              aktion,
                              erlaubt: e.target.checked,
                            })
                          }
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </div>
  );
}
