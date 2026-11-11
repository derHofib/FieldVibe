import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { accountTypenApi } from "../api/endpoints";
import { Sheet } from "../components/apple/Sheet";
import { ACCOUNT_TYP_VORLAGEN, vorlagenRechte, type AccountTypVorlage } from "../config/accountTypVorlagen";
import { aktionLabel, verstaendlicherFehler } from "../office/organigramm/darstellung";
import type { AccountTyp } from "../types";
import type { RechteRegistry } from "../types/organigramm";

interface Ergebnis {
  typ: AccountTyp;
  gesamt: number;
  fehlgeschlagen: { bereich: string; aktion: string; grund: string }[];
}

// Legt Typ + Rechte ueber die bestehenden Endpunkte an. Die Rechte laufen bewusst nacheinander:
// jede Anfrage prueft den Eskalationsschutz und aendert den Cache der Engine.
async function vorlageAnwenden(
  v: AccountTypVorlage,
  name: string,
  registry: RechteRegistry,
  fortschritt: (erledigt: number, gesamt: number) => void,
): Promise<Ergebnis> {
  const typ = await accountTypenApi.create({ name: name.trim(), ...v.flags });
  const rechte = vorlagenRechte(v, registry);
  const fehlgeschlagen: Ergebnis["fehlgeschlagen"] = [];
  for (const [i, r] of rechte.entries()) {
    try {
      await accountTypenApi.setRecht(typ.id, r.bereich, r.aktion, true);
    } catch (err) {
      fehlgeschlagen.push({ ...r, grund: verstaendlicherFehler(err) });
    }
    fortschritt(i + 1, rechte.length);
  }
  return { typ, gesamt: rechte.length, fehlgeschlagen };
}

/** "Vorlage anlegen": waehlt eine der Systemvorlagen und erzeugt daraus einen normalen Account-Typ. */
export function AccountTypVorlageSheet({
  registry,
  onClose,
  onAngelegt,
}: {
  registry: RechteRegistry | undefined;
  onClose: () => void;
  onAngelegt: (typ: AccountTyp) => void;
}) {
  const queryClient = useQueryClient();
  const [auswahl, setAuswahl] = useState<AccountTypVorlage>(ACCOUNT_TYP_VORLAGEN[0]);
  const [nameFehler, setNameFehler] = useState<string | null>(null);
  const [name, setName] = useState(ACCOUNT_TYP_VORLAGEN[0].name);
  const [fortschritt, setFortschritt] = useState<[number, number] | null>(null);
  const [ergebnis, setErgebnis] = useState<Ergebnis | null>(null);

  const anlegen = useMutation({
    mutationFn: () => vorlageAnwenden(auswahl, name, registry!, (a, b) => setFortschritt([a, b])),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["account-typen"] });
      queryClient.invalidateQueries({ queryKey: ["account-typ-rechte", r.typ.id] });
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
      if (r.fehlgeschlagen.length === 0) onAngelegt(r.typ);
      else setErgebnis(r);
    },
  });

  function waehlen(v: AccountTypVorlage) {
    setAuswahl(v);
    setName(v.name);
  }

  const anzahlRechte = registry ? vorlagenRechte(auswahl, registry).length : 0;

  return (
    <Sheet
      offen
      onClose={ergebnis ? () => onAngelegt(ergebnis.typ) : onClose}
      titel="Vorlage anlegen"
      links={
        !ergebnis && (
          <button type="button" onClick={onClose} disabled={anlegen.isPending} className="text-zeile text-tint-text disabled:opacity-40">
            Abbrechen
          </button>
        )
      }
      rechts={
        ergebnis ? (
          <button type="button" onClick={() => onAngelegt(ergebnis.typ)} className="text-zeile font-semibold text-tint-text">
            Fertig
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              if (!name.trim()) {
                setNameFehler("Bitte einen Namen eingeben.");
                return;
              }
              setNameFehler(null);
              anlegen.mutate();
            }}
            disabled={!registry || anlegen.isPending}
            className="text-zeile font-semibold text-tint-text disabled:opacity-40"
          >
            Anlegen
          </button>
        )
      }
    >
      <div className="space-y-4 p-4">
        {ergebnis ? (
          <div role="alert" className="space-y-2 text-fliess">
            <p className="font-medium text-st-arbeit">
              „{ergebnis.typ.name}“ wurde angelegt, aber {ergebnis.fehlgeschlagen.length} von {ergebnis.gesamt} Rechten konnten nicht gesetzt werden.
            </p>
            <p className="text-label2">{ergebnis.fehlgeschlagen[0].grund}</p>
            <ul className="list-disc pl-5 text-label2">
              {ergebnis.fehlgeschlagen.slice(0, 10).map((f) => (
                <li key={`${f.bereich}.${f.aktion}`}>
                  {registry?.bereiche.find((b) => b.key === f.bereich)?.label ?? f.bereich} – {aktionLabel(f.aktion)}
                </li>
              ))}
              {ergebnis.fehlgeschlagen.length > 10 && <li>… und {ergebnis.fehlgeschlagen.length - 10} weitere</li>}
            </ul>
          </div>
        ) : (
          <>
            <p className="text-sekundaer text-label2">
              Die Vorlage legt einen normalen Account-Typ mit sinnvollen Rechten an. Danach lässt er sich frei ändern. Sie können nur Rechte vergeben,
              die Sie selbst besitzen.
            </p>
            <fieldset className="space-y-2">
              <legend className="mb-1 text-fliess font-medium text-label">Vorlage</legend>
              {ACCOUNT_TYP_VORLAGEN.map((v) => (
                <label
                  key={v.key}
                  className={`flex cursor-pointer items-start gap-3 rounded-[10px] border-[0.5px] p-3 ${
                    auswahl.key === v.key ? "border-tint bg-tintbg" : "border-sep bg-card"
                  }`}
                >
                  <input
                    type="radio"
                    name="vorlage"
                    checked={auswahl.key === v.key}
                    onChange={() => waehlen(v)}
                    className="mt-1 h-4 w-4 accent-tint"
                  />
                  <span>
                    <span className="block font-semibold text-label">{v.name}</span>
                    <span className="block text-sekundaer text-label2">{v.beschreibung}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <div>
              <label htmlFor="vorlage-name" className="mb-1 block text-fliess font-medium text-label">
                Name des Account-Typs <span aria-hidden="true" className="text-st-fehlt">*</span>
              </label>
              <input
                id="vorlage-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={!!nameFehler}
                aria-describedby={nameFehler ? "vorlage-name-fehler" : undefined}
                className="field-ap"
              />
              {nameFehler && (
                <p id="vorlage-name-fehler" role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                  {nameFehler}
                </p>
              )}
              <p className="mt-1 text-sekundaer text-label2">{registry ? `${anzahlRechte} Rechte werden gesetzt.` : "Rechte-Registry lädt…"}</p>
            </div>
            {anlegen.isPending && fortschritt && (
              <p role="status" className="text-sekundaer text-label2">
                Rechte werden gesetzt … {fortschritt[0]}/{fortschritt[1]}
              </p>
            )}
            {anlegen.isError && (
              <p role="alert" className="text-fliess text-st-fehlt">
                {verstaendlicherFehler(anlegen.error, "Vorlage konnte nicht angelegt werden")}
              </p>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}
