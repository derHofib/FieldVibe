import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, LayoutTemplate, UserCog } from "lucide-react";
import { Link } from "react-router-dom";

import { accountTypenApi, organigrammApi, rechteApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { aktionLabel, verstaendlicherFehler } from "../office/organigramm/darstellung";
import { aktionsSpalten, bereichKennt } from "../office/organigramm/rechteMatrix";
import type { AccountTyp } from "../types";
import type { RechteRegistry } from "../types/organigramm";
import { AccountTypVorlageSheet } from "./AccountTypVorlageSheet";

// Hinweise zu Aktionen, die nicht selbsterklaerend sind (Spaltenkopf-Tooltip).
const AKTION_HINWEIS: Record<string, string> = {
  zeitplan_sehen: "Lesender Zugriff auf Projekt-Zeitpläne, auch ohne „Projekte: Sehen“.",
  zeitplan_beantragen: "Verschiebungen, Dauer-Änderungen und Probleme melden; das Büro entscheidet.",
  rechte_verwalten: "Rechte und Account-Typen vergeben (Eskalationsschutz: nur, was man selbst hat).",
  freigeben: "Freigabe-Schritte ausführen (z. B. Angebote, Zeitplan-Anträge).",
  exportieren: "Daten exportieren.",
};

function RechteMatrixEditor({ accountTypId, registry }: { accountTypId: string; registry: RechteRegistry }) {
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const { data: rechte, isLoading } = useQuery({
    queryKey: ["account-typ-rechte", accountTypId],
    queryFn: () => accountTypenApi.getRechte(accountTypId),
  });

  const setMutation = useMutation({
    mutationFn: ({ bereich, aktion, erlaubt }: { bereich: string; aktion: string; erlaubt: boolean }) =>
      accountTypenApi.setRecht(accountTypId, bereich, aktion, erlaubt),
    onSuccess: (data) => {
      setFehler(null);
      queryClient.setQueryData(["account-typ-rechte", accountTypId], data);
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
      queryClient.invalidateQueries({ queryKey: ["org-position"] });
    },
    onError: (err) => setFehler(verstaendlicherFehler(err, "Recht konnte nicht gespeichert werden")),
  });

  const spalten = useMemo(() => aktionsSpalten(registry), [registry]);

  function istErlaubt(bereich: string, aktion: string): boolean {
    return rechte?.find((e) => e.bereich === bereich && e.aktion === aktion)?.erlaubt ?? false;
  }

  if (isLoading) return <p className="p-4 text-sm text-label2">Lädt…</p>;

  return (
    <div className="border-t border-sep">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Rechte-Matrix des Account-Typs je Bereich und Aktion</caption>
          <thead className="text-xs text-label2">
            <tr>
              <th scope="col" className="px-4 py-2">
                Bereich
              </th>
              {spalten.map((aktion) => (
                <th key={aktion} scope="col" title={AKTION_HINWEIS[aktion]} className="px-2 py-2 text-center font-medium">
                  {aktionLabel(aktion)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-sep">
            {registry.bereiche.map((bereich) => (
              <tr key={bereich.key}>
                <th scope="row" className="px-4 py-2 text-left font-medium text-label">
                  {bereich.label}
                </th>
                {spalten.map((aktion) => (
                  <td key={aktion} className="px-2 py-2 text-center">
                    {bereichKennt(registry, bereich.key, aktion) ? (
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-tint"
                        aria-label={`${bereich.label}: ${aktionLabel(aktion)}`}
                        checked={istErlaubt(bereich.key, aktion)}
                        disabled={setMutation.isPending}
                        onChange={(e) => setMutation.mutate({ bereich: bereich.key, aktion, erlaubt: e.target.checked })}
                      />
                    ) : (
                      <span className="text-label3" aria-label="Nicht verfügbar">
                        –
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {fehler && (
        <p role="alert" className="border-t border-sep px-4 py-2 text-sm text-st-fehlt">
          {fehler}
        </p>
      )}
      <p className="border-t border-sep px-4 py-3 text-xs text-label2">
        Die Reichweite (Scope) neuer Rechte setzt das Backend automatisch: „Eigene“ bei „Sieht nur zugewiesene Kunden“ (sofern der Bereich das kennt),
        sonst „Mandant“. Feinere Reichweiten je Position vergeben Sie im Organigramm (Reiter „Rechte“).
      </p>
    </div>
  );
}

function FlagZeile({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-2 border-t border-sep px-4 py-3 text-sm text-label">
      <input type="checkbox" className="h-4 w-4 accent-tint" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  );
}

export function AccountTypenPage() {
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const { data: typen, isLoading } = useQuery({
    queryKey: ["account-typen"],
    queryFn: accountTypenApi.list,
  });
  const { data: registry } = useQuery({ queryKey: ["rechte-registry"], queryFn: rechteApi.registry, staleTime: 5 * 60 * 1000 });
  // Verwendung: wie viele Positionen im Organigramm den Typ als Vorlage nutzen (nur mit Organigramm-Recht abrufbar).
  const { data: positionen } = useQuery({
    queryKey: ["org-positionen"],
    queryFn: () => organigrammApi.positionen(),
    enabled: hatRecht("organigramm", "sehen"),
  });
  const positionenJeTyp = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of positionen ?? []) if (p.account_typ) m.set(p.account_typ.id, (m.get(p.account_typ.id) ?? 0) + 1);
    return m;
  }, [positionen]);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [zeigeVorlage, setZeigeVorlage] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [nurZugewieseneKunden, setNurZugewieseneKunden] = useState(false);
  const [darfSelbstUebernehmen, setDarfSelbstUebernehmen] = useState(false);
  const [darfZeitenBuchen, setDarfZeitenBuchen] = useState(false);
  const [darfAbwesenheiten, setDarfAbwesenheiten] = useState(false);

  const createMutation = useMutation({
    mutationFn: accountTypenApi.create,
    onSuccess: (typ: AccountTyp) => {
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
      setName("");
      setIcon("");
      setNurZugewieseneKunden(false);
      setDarfSelbstUebernehmen(false);
      setDarfZeitenBuchen(false);
      setDarfAbwesenheiten(false);
      setExpandedId(typ.id);
    },
    onError: (err) => setFormError(err instanceof ApiError ? verstaendlicherFehler(err) : "Fehler"),
  });

  const [updateError, setUpdateError] = useState<string | null>(null);
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      nur_zugewiesene_kunden?: boolean;
      darf_vorgaenge_selbst_uebernehmen?: boolean;
      darf_zeiten_buchen?: boolean;
      darf_abwesenheiten_verwalten?: boolean;
    }) => accountTypenApi.update(id, body),
    onSuccess: () => {
      setUpdateError(null);
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      queryClient.invalidateQueries({ queryKey: ["account-typ-rechte"] });
    },
    onError: (err) => setUpdateError(verstaendlicherFehler(err, "Änderung fehlgeschlagen")),
  });

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    mutationFn: accountTypenApi.remove,
    onSuccess: () => {
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
    },
    onError: (err) => setDeleteError(verstaendlicherFehler(err, "Löschen fehlgeschlagen")),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createMutation.mutate({
      name,
      icon: icon.trim() || null,
      nur_zugewiesene_kunden: nurZugewieseneKunden,
      darf_vorgaenge_selbst_uebernehmen: darfSelbstUebernehmen,
      darf_zeiten_buchen: darfZeitenBuchen,
      darf_abwesenheiten_verwalten: darfAbwesenheiten,
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <Link to="/einstellungen" className="text-sm font-medium text-tint-text hover:underline">
            ← Zurück zu Einstellungen
          </Link>
          <h1 className="mt-2 text-lg font-bold text-label">Account-Typen & Rechte</h1>
          <p className="mt-1 text-sm text-label2">
            Ein Account-Typ ist die Rechte-Vorlage für Positionen im Organigramm: Er legt je Bereich fest, was sehen, erstellen, bearbeiten, löschen,
            exportieren oder freigeben darf. Einzelne Positionen und Nutzer können davon abweichen. mandant_admin ist von dieser Matrix nicht betroffen
            und hat immer vollen Zugriff.
          </p>
        </div>
        <button type="button" className="btn-ap" onClick={() => setZeigeVorlage(true)}>
          <LayoutTemplate size={14} strokeWidth={2} aria-hidden="true" />
          Vorlage anlegen
        </button>
      </div>

      <section className="card-ap p-4">
        <h2 className="mb-3 text-sm font-bold text-label">Neuen Account-Typ anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="at-name" className="mb-1 block text-sm font-medium text-label">
              Name
            </label>
            <input id="at-name" required placeholder="z.B. Techniker" value={name} onChange={(e) => setName(e.target.value)} className="field-ap w-56" />
          </div>
          <div>
            <label htmlFor="at-icon" className="mb-1 block text-sm font-medium text-label">
              Icon (optional)
            </label>
            <input id="at-icon" placeholder="🔧" value={icon} onChange={(e) => setIcon(e.target.value)} className="field-ap w-20" />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input type="checkbox" className="h-4 w-4 accent-tint" checked={nurZugewieseneKunden} onChange={(e) => setNurZugewieseneKunden(e.target.checked)} />
            Sieht nur zugewiesene Kunden
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input type="checkbox" className="h-4 w-4 accent-tint" checked={darfSelbstUebernehmen} onChange={(e) => setDarfSelbstUebernehmen(e.target.checked)} />
            Darf Aufträge selbst übernehmen
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input type="checkbox" className="h-4 w-4 accent-tint" checked={darfZeitenBuchen} onChange={(e) => setDarfZeitenBuchen(e.target.checked)} />
            Darf Zeiten buchen
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-label">
            <input type="checkbox" className="h-4 w-4 accent-tint" checked={darfAbwesenheiten} onChange={(e) => setDarfAbwesenheiten(e.target.checked)} />
            Abwesenheiten verwalten
          </label>
          <button type="submit" disabled={createMutation.isPending} className="btn-ap-primary">
            Anlegen
          </button>
        </form>
        {formError && (
          <p role="alert" className="mt-2 text-sm text-st-fehlt">
            {formError}
          </p>
        )}
      </section>

      <section className="space-y-3">
        {deleteError && (
          <p role="alert" className="text-sm text-st-fehlt">
            {deleteError}
          </p>
        )}
        {updateError && (
          <p role="alert" className="text-sm text-st-fehlt">
            {updateError}
          </p>
        )}
        {isLoading ? (
          <p className="text-label2">Lädt…</p>
        ) : typen && typen.length > 0 ? (
          typen.map((typ) => {
            const offen = expandedId === typ.id;
            const anzahlPositionen = positionenJeTyp.get(typ.id) ?? 0;
            return (
              <div key={typ.id} className="card-ap">
                <div className="flex items-center gap-3 p-4">
                  <button
                    type="button"
                    onClick={() => setExpandedId(offen ? null : typ.id)}
                    aria-expanded={offen}
                    aria-controls={`typ-${typ.id}`}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    {typ.icon ? (
                      <span className="text-xl" aria-hidden="true">
                        {typ.icon}
                      </span>
                    ) : (
                      <UserCog size={20} strokeWidth={1.75} className="shrink-0 text-label2" aria-hidden="true" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-label">{typ.name}</span>
                      <span className="block text-xs text-label2">
                        {typ.anzahl_nutzer} Nutzer
                        {positionen && ` · von ${anzahlPositionen} ${anzahlPositionen === 1 ? "Position" : "Positionen"} genutzt`}
                        {typ.nur_zugewiesene_kunden && " · nur zugewiesene Kunden"}
                        {typ.darf_vorgaenge_selbst_uebernehmen && " · darf Aufträge selbst übernehmen"}
                        {typ.darf_zeiten_buchen && " · darf Zeiten buchen"}
                        {typ.darf_abwesenheiten_verwalten && " · verwaltet Abwesenheiten"}
                      </span>
                    </span>
                    {offen ? <ChevronUp size={16} className="shrink-0 text-label2" aria-hidden="true" /> : <ChevronDown size={16} className="shrink-0 text-label2" aria-hidden="true" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`Account-Typ "${typ.name}" wirklich löschen? Das kann nicht rückgängig gemacht werden.`)) {
                        setDeleteError(null);
                        deleteMutation.mutate(typ.id);
                      }
                    }}
                    disabled={typ.anzahl_nutzer > 0}
                    title={typ.anzahl_nutzer > 0 ? "Diesem Account-Typ sind noch Nutzer zugeordnet" : undefined}
                    className="btn-ap shrink-0 !border-st-fehlt text-st-fehlt disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Löschen
                  </button>
                </div>
                {offen && (
                  <div id={`typ-${typ.id}`}>
                    <FlagZeile
                      checked={typ.nur_zugewiesene_kunden}
                      onChange={(v) => updateMutation.mutate({ id: typ.id, nur_zugewiesene_kunden: v })}
                    >
                      Sieht nur zugewiesene Kunden (Reichweite „Eigene“ statt „Mandant“)
                    </FlagZeile>
                    <FlagZeile
                      checked={typ.darf_vorgaenge_selbst_uebernehmen}
                      onChange={(v) => updateMutation.mutate({ id: typ.id, darf_vorgaenge_selbst_uebernehmen: v })}
                    >
                      Darf Aufträge selbst übernehmen ("Ticket übernehmen"-Button)
                    </FlagZeile>
                    <FlagZeile checked={typ.darf_zeiten_buchen} onChange={(v) => updateMutation.mutate({ id: typ.id, darf_zeiten_buchen: v })}>
                      Darf Zeiten buchen (Vormerken/Buchen im Zeit-Tab, unabhängig von Rolle/Gerät)
                    </FlagZeile>
                    <FlagZeile
                      checked={typ.darf_abwesenheiten_verwalten}
                      onChange={(v) => updateMutation.mutate({ id: typ.id, darf_abwesenheiten_verwalten: v })}
                    >
                      Abwesenheiten verwalten (Soll-Zeit, Feiertage und Bundesland pflegen, Saldo anderer einsehen)
                    </FlagZeile>
                    {registry ? <RechteMatrixEditor accountTypId={typ.id} registry={registry} /> : <p className="border-t border-sep p-4 text-sm text-label2">Rechte-Registry lädt…</p>}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <p className="text-sm text-label2">Noch keine Account-Typen angelegt.</p>
        )}
      </section>

      {zeigeVorlage && (
        <AccountTypVorlageSheet
          registry={registry}
          onClose={() => setZeigeVorlage(false)}
          onAngelegt={(typ) => {
            setZeigeVorlage(false);
            setExpandedId(typ.id);
          }}
        />
      )}
    </div>
  );
}
