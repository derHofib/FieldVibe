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
  "formulare",
  "partner",
  "projekte",
];
const BEREICH_LABEL: Record<RechteBereich, string> = {
  vorgaenge: "Aufträge",
  kunden: "Kunden & Anlagen",
  material: "Material",
  dispo: "Dispo/Termine",
  abrechnung: "Angebote & Rechnungen",
  statistik: "Statistik & Exporte",
  mitarbeiterverwaltung: "Mitarbeiterliste",
  formulare: "Formular-Baukasten",
  partner: "Partner & Nachunternehmer",
  projekte: "Projekte",
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

  if (isLoading) return <p className="p-4 text-sm text-label2">Lädt…</p>;

  return (
    <div className="overflow-x-auto border-t border-sep">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-label2">
          <tr>
            <th className="px-4 py-2">Bereich</th>
            {AKTIONEN.map((aktion) => (
              <th key={aktion} className="px-3 py-2 text-center">
                {AKTION_LABEL[aktion]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-sep">
          {BEREICHE.map((bereich) => (
            <tr key={bereich}>
              <td className="px-4 py-2 font-medium text-label">
                {BEREICH_LABEL[bereich]}
              </td>
              {AKTIONEN.map((aktion) => (
                <td key={aktion} className="px-3 py-2 text-center">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-ind-acc"
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
  const [darfSelbstUebernehmen, setDarfSelbstUebernehmen] = useState(false);

  const createMutation = useMutation({
    mutationFn: accountTypenApi.create,
    onSuccess: (typ: AccountTyp) => {
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      setName("");
      setIcon("");
      setNurZugewieseneKunden(false);
      setDarfSelbstUebernehmen(false);
      setExpandedId(typ.id);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...body }: { id: string; darf_vorgaenge_selbst_uebernehmen: boolean }) =>
      accountTypenApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["account-typen"] }),
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
      darf_vorgaenge_selbst_uebernehmen: darfSelbstUebernehmen,
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/einstellungen" className="text-sm font-medium text-tint-text hover:underline">
          ← Zurück zu Einstellungen
        </Link>
        <h1 className="mt-2 text-lg font-bold text-label">Account-Typen & Rechte</h1>
        <p className="mt-1 text-sm text-label2">
          Definiere beliebig viele eigene Account-Typen (z.B. "Techniker", "Bürokraft") und lege je Typ
          fest, was er in jedem Funktionsbereich sehen, erstellen, bearbeiten und löschen darf.
          mandant_admin ist von dieser Matrix nicht betroffen und hat immer vollen Zugriff.
        </p>
      </div>

      <section className="card-ap p-4">
        <h2 className="mb-3 text-sm font-bold text-label">Neuen Account-Typ anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Name</label>
            <input
              required
              placeholder="z.B. Techniker"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">
              Icon (optional)
            </label>
            <input
              placeholder="🔧"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              className="btn-touch w-20 border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input
              type="checkbox"
              className="h-4 w-4 accent-ind-acc"
              checked={nurZugewieseneKunden}
              onChange={(e) => setNurZugewieseneKunden(e.target.checked)}
            />
            Sieht nur zugewiesene Kunden
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input
              type="checkbox"
              className="h-4 w-4 accent-ind-acc"
              checked={darfSelbstUebernehmen}
              onChange={(e) => setDarfSelbstUebernehmen(e.target.checked)}
            />
            Darf Aufträge selbst übernehmen
          </label>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch btn-ap-primary"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-st-fehlt ">{formError}</p>}
      </section>

      <section className="space-y-3">
        {deleteError && <p className="text-sm text-st-fehlt ">{deleteError}</p>}
        {isLoading ? (
          <p className="text-label2">Lädt…</p>
        ) : typen && typen.length > 0 ? (
          typen.map((typ) => (
            <div
              key={typ.id}
              className="card-ap"
            >
              <button
                onClick={() => setExpandedId(expandedId === typ.id ? null : typ.id)}
                className="btn-touch flex w-full items-center gap-3 p-4 text-left"
              >
                <span className="text-xl">{typ.icon || "🧩"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-label">{typ.name}</span>
                  <span className="block text-xs text-label2">
                    {typ.anzahl_nutzer} {typ.anzahl_nutzer === 1 ? "Nutzer" : "Nutzer"}
                    {typ.nur_zugewiesene_kunden && " · nur zugewiesene Kunden"}
                    {typ.darf_vorgaenge_selbst_uebernehmen && " · darf Aufträge selbst übernehmen"}
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
                  className="btn-touch border border-st-fehlt px-3 py-2 text-xs font-semibold text-st-fehlt hover:bg-st-fehlt-bg disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-st-fehlt-dot"
                >
                  Löschen
                </button>
                <span className="text-label2">
                  {expandedId === typ.id ? "▲" : "▼"}
                </span>
              </button>
              {expandedId === typ.id && (
                <>
                  <label className="flex items-center gap-2 border-t border-sep px-4 py-3 text-sm text-label">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-ind-acc"
                      checked={typ.darf_vorgaenge_selbst_uebernehmen}
                      onChange={(e) =>
                        updateMutation.mutate({
                          id: typ.id,
                          darf_vorgaenge_selbst_uebernehmen: e.target.checked,
                        })
                      }
                    />
                    Darf Aufträge selbst übernehmen ("Ticket übernehmen"-Button)
                  </label>
                  <RechteMatrixEditor accountTypId={typ.id} />
                </>
              )}
            </div>
          ))
        ) : (
          <p className="text-sm text-label2">
            Noch keine Account-Typen angelegt.
          </p>
        )}
      </section>
    </div>
  );
}
