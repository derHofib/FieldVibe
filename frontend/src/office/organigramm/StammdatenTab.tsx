import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { organigrammApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { Switch } from "../../components/apple/Switch";
import type { AccountTyp } from "../../types";
import type { OrgEinheit, PositionDetail, PositionTyp } from "../../types/organigramm";
import { verstaendlicherFehler } from "./darstellung";
import { formAusPosition, updateAusFormular, type StammdatenForm } from "./stammdaten";

function Feld({ id, label, hinweis, children }: { id: string; label: string; hinweis?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-label">
        {label}
      </label>
      {children}
      {hinweis && <p className="mt-1 text-xs text-label2">{hinweis}</p>}
    </div>
  );
}

export function StammdatenTab({
  detail,
  orgEinheiten,
  accountTypen,
  darfBearbeiten,
  darfRechteVerwalten,
  onGespeichert,
}: {
  detail: PositionDetail;
  orgEinheiten: OrgEinheit[];
  accountTypen: AccountTyp[];
  darfBearbeiten: boolean;
  darfRechteVerwalten: boolean;
  onGespeichert: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StammdatenForm>(() => formAusPosition(detail));
  const [fehler, setFehler] = useState<string | null>(null);
  const [gespeichert, setGespeichert] = useState(false);

  // Nach Neuladen (Speichern, Umhaengen) den Serverstand uebernehmen.
  useEffect(() => setForm(formAusPosition(detail)), [detail]);

  const aenderung = updateAusFormular(detail, form);
  const dirty = Object.keys(aenderung).length > 0;
  const schreibgeschuetzt = !darfBearbeiten || !!detail.archiviert_am;
  const istWurzel = detail.parent_id === null;

  const speichern = useMutation({
    mutationFn: () => organigrammApi.updatePosition(detail.id, aenderung),
    onSuccess: () => {
      setFehler(null);
      setGespeichert(true);
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
      onGespeichert();
    },
    onError: (err) => {
      setGespeichert(false);
      setFehler(verstaendlicherFehler(err, "Speichern fehlgeschlagen"));
    },
  });

  const set = <K extends keyof StammdatenForm>(k: K, v: StammdatenForm[K]) => {
    setGespeichert(false);
    setForm((f) => ({ ...f, [k]: v }));
  };

  function absenden(e: FormEvent) {
    e.preventDefault();
    if (dirty && form.titel.trim()) speichern.mutate();
  }

  return (
    <form
      onSubmit={absenden}
      role="tabpanel"
      id="org-tabpanel-stammdaten"
      aria-labelledby="org-tab-stammdaten"
      className="space-y-4 p-4"
    >
      <fieldset disabled={schreibgeschuetzt} className="space-y-4 disabled:opacity-80">
        <Feld id="sd-titel" label="Titel">
          <input id="sd-titel" required value={form.titel} onChange={(e) => set("titel", e.target.value)} className="field-ap" />
        </Feld>

        <div>
          <span className="mb-1 block text-sm font-medium text-label">Typ</span>
          <SegmentedControl<PositionTyp>
            ariaLabel="Positionstyp"
            optionen={[
              { wert: "linie", label: "Linie" },
              { wert: "stabsstelle", label: "Stabsstelle" },
            ]}
            wert={form.typ}
            onChange={(t) => !istWurzel && set("typ", t)}
          />
          <p className="mt-1 text-xs text-label2">
            {istWurzel
              ? "Die Wurzel bleibt immer eine Linienposition."
              : "Stabsstellen stehen seitlich neben ihrer übergeordneten Position, außerhalb der Linie."}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Feld id="sd-ebene" label="Ebene">
            <input id="sd-ebene" type="number" value={form.ebene} onChange={(e) => set("ebene", e.target.value)} className="field-ap" />
          </Feld>
          <Feld id="sd-reihenfolge" label="Reihenfolge">
            <input id="sd-reihenfolge" type="number" value={form.reihenfolge} onChange={(e) => set("reihenfolge", e.target.value)} className="field-ap" />
          </Feld>
        </div>

        <Feld id="sd-einheit" label="Organisationseinheit">
          <select id="sd-einheit" value={form.orgEinheitId} onChange={(e) => set("orgEinheitId", e.target.value)} className="field-ap">
            <option value="">Keine</option>
            {orgEinheiten.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </Feld>

        <Feld
          id="sd-typ"
          label="Account-Typ (Rechte-Vorlage)"
          hinweis={darfRechteVerwalten ? undefined : "Ändern erfordert das Recht „Rechte verwalten“."}
        >
          <select
            id="sd-typ"
            value={form.accountTypId}
            onChange={(e) => set("accountTypId", e.target.value)}
            disabled={!darfRechteVerwalten}
            className="field-ap"
          >
            <option value="">Keiner</option>
            {accountTypen.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Feld>

        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-label">Platzhalter (geplant)</p>
            <p className="text-xs text-label2">Geplante Position ohne Besetzung; dient als Vorlage.</p>
          </div>
          <Switch checked={form.geplant} onChange={(v) => set("geplant", v)} ariaLabel="Platzhalter (geplant)" />
        </div>

        <Feld id="sd-soll" label="Soll-Besetzung">
          <input id="sd-soll" type="number" min={0} value={form.sollBesetzung} onChange={(e) => set("sollBesetzung", e.target.value)} className="field-ap w-28" />
        </Feld>

        <div className="grid grid-cols-2 gap-3">
          <Feld id="sd-ab" label="Gültig ab">
            <input id="sd-ab" type="date" value={form.gueltigAb} onChange={(e) => set("gueltigAb", e.target.value)} className="field-ap" />
          </Feld>
          <Feld id="sd-bis" label="Gültig bis">
            <input id="sd-bis" type="date" value={form.gueltigBis} onChange={(e) => set("gueltigBis", e.target.value)} className="field-ap" />
          </Feld>
        </div>
      </fieldset>

      {detail.archiviert_am && <p className="text-sm text-label2">Archivierte Positionen können nicht bearbeitet werden.</p>}
      {fehler && (
        <p role="alert" className="text-sm text-st-fehlt">
          {fehler}
        </p>
      )}
      {!schreibgeschuetzt && (
        <div className="flex items-center gap-3">
          <button type="submit" disabled={!dirty || speichern.isPending || !form.titel.trim()} className="btn-ap-primary">
            Speichern
          </button>
          {gespeichert && !dirty && (
            <span role="status" className="text-sm text-st-erledigt">
              Gespeichert
            </span>
          )}
        </div>
      )}
    </form>
  );
}
