import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { accountTypenApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { AccountTyp, RechteAktion, RechteBereich } from "../types";

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
const AKTIONEN: RechteAktion[] = ["sehen", "erstellen", "bearbeiten", "loeschen"];
const AKTION_LABEL: Record<RechteAktion, string> = {
  sehen: "Sehen",
  erstellen: "Erstellen",
  bearbeiten: "Bearbeiten",
  loeschen: "Löschen",
};

function RechteMatrixEditor({ accountTypId }: { accountTypId: string }) {
  const queryClient = useQueryClient();
  const { data: rechte, isLoading } = useQuery({
    queryKey: ["account-typ-rechte", accountTypId],
    queryFn: () => accountTypenApi.getRechte(accountTypId),
  });

  const setMutation = useMutation({
    mutationFn: ({
      bereich,
      aktion,
      erlaubt,
    }: {
      bereich: RechteBereich;
      aktion: RechteAktion;
      erlaubt: boolean;
    }) => accountTypenApi.setRecht(accountTypId, bereich, aktion, erlaubt),
    onSuccess: (data) => queryClient.setQueryData(["account-typ-rechte", accountTypId], data),
  });

  function istErlaubt(bereich: RechteBereich, aktion: RechteAktion): boolean {
    return rechte?.find((e) => e.bereich === bereich && e.aktion === aktion)?.erlaubt ?? false;
  }

  if (isLoading) return <p className="p-4 text-sm text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="overflow-x-auto border-t border-slate-100 dark:border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
          <tr>
            <th className="px-4 py-2">Bereich</th>
            {AKTIONEN.map((aktion) => (
              <th key={aktion} className="px-3 py-2 text-center">
                {AKTION_LABEL[aktion]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {BEREICHE.map((bereich) => (
            <tr key={bereich}>
              <td className="px-4 py-2 font-medium text-slate-700 dark:text-slate-300">
                {BEREICH_LABEL[bereich]}
              </td>
              {AKTIONEN.map((aktion) => (
                <td key={aktion} className="px-3 py-2 text-center">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-cyan-600"
                    checked={istErlaubt(bereich, aktion)}
                    disabled={setMutation.isPending}
                    onChange={(e) =>
                      setMutation.mutate({ bereich, aktion, erlaubt: e.target.checked })
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AccountTypenPage() {
  const queryClient = useQueryClient();
  const { data: typen, isLoading } = useQuery({
    queryKey: ["account-typen"],
    queryFn: accountTypenApi.list,
  });

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [nurZugewieseneKunden, setNurZugewieseneKunden] = useState(false);

  const createMutation = useMutation({
    mutationFn: accountTypenApi.create,
    onSuccess: (typ: AccountTyp) => {
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      setName("");
      setIcon("");
      setNurZugewieseneKunden(false);
      setExpandedId(typ.id);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    mutationFn: accountTypenApi.remove,
    onSuccess: () => {
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
    },
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createMutation.mutate({
      name,
      icon: icon.trim() || null,
      nur_zugewiesene_kunden: nurZugewieseneKunden,
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/einstellungen" className="text-sm font-medium text-blue-700 hover:underline dark:text-blue-400">
          ← Zurück zu Einstellungen
        </Link>
        <h1 className="mt-2 text-lg font-bold text-slate-800 dark:text-slate-100">Account-Typen & Rechte</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Definiere beliebig viele eigene Account-Typen (z.B. "Techniker", "Bürokraft") und lege je Typ
          fest, was er in jedem Funktionsbereich sehen, erstellen, bearbeiten und löschen darf.
          mandant_admin ist von dieser Matrix nicht betroffen und hat immer vollen Zugriff.
        </p>
      </div>

      <section className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-100">Neuen Account-Typ anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Name</label>
            <input
              required
              placeholder="z.B. Techniker"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Icon (optional)
            </label>
            <input
              placeholder="🔧"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              className="btn-touch w-20 rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              className="h-4 w-4 accent-cyan-600"
              checked={nurZugewieseneKunden}
              onChange={(e) => setNurZugewieseneKunden(e.target.checked)}
            />
            Sieht nur zugewiesene Kunden
          </label>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{formError}</p>}
      </section>

      <section className="space-y-3">
        {deleteError && <p className="text-sm text-red-700 dark:text-red-400">{deleteError}</p>}
        {isLoading ? (
          <p className="text-slate-500 dark:text-slate-400">Lädt…</p>
        ) : typen && typen.length > 0 ? (
          typen.map((typ) => (
            <div
              key={typ.id}
              className="overflow-hidden rounded-lg bg-white shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
            >
              <button
                onClick={() => setExpandedId(expandedId === typ.id ? null : typ.id)}
                className="btn-touch flex w-full items-center gap-3 p-4 text-left"
              >
                <span className="text-xl">{typ.icon || "🧩"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-slate-800 dark:text-slate-100">{typ.name}</span>
                  <span className="block text-xs text-slate-500 dark:text-slate-400">
                    {typ.anzahl_nutzer} {typ.anzahl_nutzer === 1 ? "Nutzer" : "Nutzer"}
                    {typ.nur_zugewiesene_kunden && " · nur zugewiesene Kunden"}
                  </span>
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (
                      window.confirm(
                        `Account-Typ "${typ.name}" wirklich löschen? Das kann nicht rückgängig gemacht werden.`,
                      )
                    ) {
                      setDeleteError(null);
                      deleteMutation.mutate(typ.id);
                    }
                  }}
                  disabled={typ.anzahl_nutzer > 0}
                  title={
                    typ.anzahl_nutzer > 0
                      ? "Diesem Account-Typ sind noch Nutzer zugeordnet"
                      : undefined
                  }
                  className="btn-touch rounded-md bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20"
                >
                  Löschen
                </button>
                <span className="text-slate-300 dark:text-slate-600">
                  {expandedId === typ.id ? "▲" : "▼"}
                </span>
              </button>
              {expandedId === typ.id && <RechteMatrixEditor accountTypId={typ.id} />}
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Noch keine Account-Typen angelegt.
          </p>
        )}
      </section>
    </div>
  );
}
