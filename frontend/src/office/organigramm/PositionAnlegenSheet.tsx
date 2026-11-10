import { useState, type FormEvent } from "react";

import { Sheet } from "../../components/apple/Sheet";
import type { AccountTyp } from "../../types";
import type { OrgEinheit, Position, PositionCreate } from "../../types/organigramm";
import { ANLEGE_MODUS_TITEL, neuePositionBody, type AnlegeModus } from "./darstellung";

export function PositionAnlegenSheet({
  modus,
  parent,
  accountTypen,
  orgEinheiten,
  darfRechteVerwalten,
  pending,
  fehler,
  onClose,
  onAnlegen,
}: {
  modus: AnlegeModus;
  parent: Position;
  accountTypen: AccountTyp[];
  orgEinheiten: OrgEinheit[];
  darfRechteVerwalten: boolean;
  pending: boolean;
  fehler: string | null;
  onClose: () => void;
  onAnlegen: (body: PositionCreate) => void;
}) {
  const [titel, setTitel] = useState("");
  const [einheit, setEinheit] = useState("");
  const [typ, setTyp] = useState("");
  const [soll, setSoll] = useState(1);

  function absenden(e: FormEvent) {
    e.preventDefault();
    if (!titel.trim()) return;
    onAnlegen(
      neuePositionBody(modus, parent.id, {
        titel,
        orgEinheitId: einheit,
        accountTypId: typ,
        sollBesetzung: soll,
      }),
    );
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel={ANLEGE_MODUS_TITEL[modus]}
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form="position-anlegen-form"
          disabled={pending || !titel.trim()}
          className="text-[17px] font-semibold text-tint-text disabled:opacity-40"
        >
          Anlegen
        </button>
      }
    >
      <form id="position-anlegen-form" onSubmit={absenden} className="space-y-4 p-4">
        <p className="text-sm text-label2">
          {modus === "stabsstelle" ? "Stabsstelle neben" : "Unterhalb von"} <span className="font-medium text-label">{parent.titel}</span>
          {modus === "platzhalter" && " – ohne Besetzung, als geplante Position (Vorlage)."}
        </p>
        <div>
          <label htmlFor="pos-titel" className="mb-1 block text-sm font-medium text-label">
            Titel
          </label>
          <input id="pos-titel" required autoFocus value={titel} onChange={(e) => setTitel(e.target.value)} className="field-ap" placeholder="z. B. Teamleitung Montage" />
        </div>
        <div>
          <label htmlFor="pos-einheit" className="mb-1 block text-sm font-medium text-label">
            Organisationseinheit (optional)
          </label>
          <select id="pos-einheit" value={einheit} onChange={(e) => setEinheit(e.target.value)} className="field-ap">
            <option value="">Keine</option>
            {orgEinheiten.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </div>
        {darfRechteVerwalten && (
          <div>
            <label htmlFor="pos-typ" className="mb-1 block text-sm font-medium text-label">
              Account-Typ (optional)
            </label>
            <select id="pos-typ" value={typ} onChange={(e) => setTyp(e.target.value)} className="field-ap">
              <option value="">Keiner</option>
              {accountTypen.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label htmlFor="pos-soll" className="mb-1 block text-sm font-medium text-label">
            Soll-Besetzung
          </label>
          <input id="pos-soll" type="number" min={0} value={soll} onChange={(e) => setSoll(Math.max(0, Number(e.target.value) || 0))} className="field-ap w-28" />
        </div>
        {fehler && (
          <p role="alert" className="text-sm text-st-fehlt">
            {fehler}
          </p>
        )}
      </form>
    </Sheet>
  );
}
