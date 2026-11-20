import { ChevronRight, Folder, Layers, Rss, X, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

import { SearchableSelect } from "../../components/SearchableSelect";
import { StatusPille } from "../../components/apple/StatusPille";
import { SymbolKachel, type KachelFarbe } from "../../components/apple/SymbolKachel";
import { VorgangStatusPille } from "../../components/VorgangStatusPille";
import type { Auftrag, AuftragStatus, ProjektAufgabe, Vorgang } from "../../types";
import { auftragLink, auftragStatusZuToken, projektLink } from "../../utils/verknuepfung";
import { AUFTRAG_STATUS_LABEL } from "../auftraege/AuftraegeTabelle";

export interface GehoertZuKette {
  projekt: { id: string | null; name: string } | null;
  auftrag: { id: string | null; titel: string; status: AuftragStatus | null } | null;
  vorgang: { id: string; nummer: string; titel: string | null; status: string | null } | null;
  /** Grauer Hinweis: der Vorgang gehört zu einem anderen Projekt als die Karte. */
  abweichung: string | null;
}

/** Kette der Aufgabe. Unveränderte Wahl kommt vom Server (`pfad_*`), eine neue Wahl wird aus der gewählten
 * Zeile abgeleitet, bis gespeichert ist; eine Kanban-Karte behält dabei ihr Projekt (die Karte gehört auf ihr Board). */
export function gehoertZuKette(opts: {
  aufgabe: ProjektAufgabe | null;
  vorgangId: string;
  auftragId: string;
  vorgaenge?: Vorgang[];
  auftraege?: Auftrag[];
}): GehoertZuKette {
  const { aufgabe, vorgangId, auftragId, vorgaenge, auftraege } = opts;
  const unveraendert = (aufgabe?.vorgang_id ?? "") === vorgangId && (aufgabe?.auftrag_id ?? "") === auftragId;
  if (unveraendert && aufgabe) {
    const projektId = aufgabe.pfad_projekt_id ?? aufgabe.projekt_id;
    const projektName = aufgabe.pfad_projekt_name ?? aufgabe.projekt_name ?? null;
    const aId = aufgabe.pfad_auftrag_id ?? aufgabe.auftrag_id;
    return {
      projekt: projektName ? { id: projektId, name: projektName } : null,
      auftrag: aufgabe.auftrag_titel ? { id: aId, titel: aufgabe.auftrag_titel, status: aufgabe.auftrag_status ?? null } : null,
      vorgang: aufgabe.vorgang_id
        ? {
            id: aufgabe.vorgang_id,
            nummer: aufgabe.vorgang_vorgangsnummer ?? "Vorgang",
            titel: aufgabe.vorgang_titel ?? null,
            status: aufgabe.vorgang_status ?? null,
          }
        : null,
      abweichung: aufgabe.pfad_abweichung_projekt_name ?? null,
    };
  }

  const kanban = aufgabe?.projekt_id
    ? { id: aufgabe.pfad_projekt_id ?? aufgabe.projekt_id, name: aufgabe.pfad_projekt_name ?? aufgabe.projekt_name ?? "" }
    : null;
  if (vorgangId) {
    const v = vorgaenge?.find((x) => x.id === vorgangId);
    const eigenesProjekt = v?.projekt_name ? { id: v.projekt_id, name: v.projekt_name } : null;
    return {
      projekt: kanban?.name ? kanban : eigenesProjekt,
      auftrag: v?.auftrag_titel ? { id: v.auftrag_id, titel: v.auftrag_titel, status: null } : null,
      vorgang: { id: vorgangId, nummer: v?.vorgangsnummer ?? "Vorgang", titel: v?.titel ?? null, status: v?.status ?? null },
      abweichung: kanban?.name && eigenesProjekt && eigenesProjekt.id !== kanban.id ? eigenesProjekt.name : null,
    };
  }
  if (auftragId) {
    const a = auftraege?.find((x) => x.id === auftragId);
    return {
      projekt: kanban?.name ? kanban : a?.projekt_name ? { id: a.projekt_id, name: a.projekt_name } : null,
      auftrag: { id: auftragId, titel: a?.titel ?? "Auftrag", status: a?.status ?? null },
      vorgang: null,
      abweichung: null,
    };
  }
  return { projekt: kanban?.name ? kanban : null, auftrag: null, vorgang: null, abweichung: null };
}

const WAHL_VORGANG = "v:";
const WAHL_AUFTRAG = "a:";

function Zeile({
  stufe,
  icon,
  farbe,
  art,
  titel,
  pille,
  ziel,
  navigate,
}: {
  stufe: 0 | 1 | 2;
  icon: LucideIcon;
  farbe: KachelFarbe;
  art: string;
  titel: string;
  pille?: ReactNode;
  ziel: string | null;
  navigate: (to: string) => void;
}) {
  const inhalt = (
    <>
      <SymbolKachel icon={icon} farbe={farbe} groesse={28} />
      <span className="min-w-0 flex-1 text-left">
        <span className="block text-meta text-label2">{art}</span>
        <span className="block truncate text-fliess font-semibold text-label">{titel}</span>
      </span>
      {pille}
      {ziel && <ChevronRight size={14} strokeWidth={2} className="shrink-0 text-label3" aria-hidden="true" />}
    </>
  );
  const klasse = "flex w-full items-center gap-2.5 rounded-[var(--radius-ap-card)] bg-fill px-2.5 py-2";
  return (
    // Einrückung je Stufe: die Kette liest sich als Baum Projekt > Auftrag > Vorgang.
    <div style={{ marginLeft: stufe * 16 }}>
      {ziel ? (
        <button type="button" onClick={() => navigate(ziel)} className={`${klasse} hover:bg-fill2`}>
          {inhalt}
        </button>
      ) : (
        <div className={klasse}>{inhalt}</div>
      )}
    </div>
  );
}

/** Abschnitt "Gehört zu" im Aufgaben-Panel: Kette Projekt > Auftrag > Vorgang und "Ändern" über ein einziges
 * Suchfeld. Vorgang wählen setzt den Vorgang (Auftrag und Projekt ergeben sich daraus), Auftrag wählen setzt den
 * Auftrag und leert den Vorgang -- beides gleichzeitig lehnt der Server ab. Projekt und Auftrag sind nur mit
 * `linksAktiv` klickbar. */
export function AufgabeGehoertZu({
  aufgabe,
  vorgangId,
  auftragId,
  vorgaenge,
  auftraege,
  onWaehleVorgang,
  onWaehleAuftrag,
  onEntfernen,
  linksAktiv,
  navigate,
  extraAktion,
}: {
  aufgabe: ProjektAufgabe | null;
  vorgangId: string;
  auftragId: string;
  vorgaenge?: Vorgang[];
  auftraege?: Auftrag[];
  onWaehleVorgang: (id: string) => void;
  onWaehleAuftrag: (id: string) => void;
  onEntfernen: () => void;
  linksAktiv: boolean;
  navigate: (to: string) => void;
  /** z. B. "+ Neuen Vorgang aus dieser Aufgabe anlegen". */
  extraAktion?: ReactNode;
}) {
  const kette = gehoertZuKette({ aufgabe, vorgangId, auftragId, vorgaenge, auftraege });
  const [aendern, setAendern] = useState(false);
  const leer = !kette.projekt && !kette.auftrag && !kette.vorgang;

  const optionen = [
    ...(vorgaenge ?? []).map((v) => ({ value: `${WAHL_VORGANG}${v.id}`, label: `${v.vorgangsnummer} · ${v.titel}`, sublabel: "Vorgang" })),
    ...(auftraege ?? []).map((a) => ({ value: `${WAHL_AUFTRAG}${a.id}`, label: a.titel, sublabel: "Auftrag" })),
  ];
  function gewaehlt(wert: string) {
    if (wert.startsWith(WAHL_VORGANG)) onWaehleVorgang(wert.slice(WAHL_VORGANG.length));
    else if (wert.startsWith(WAHL_AUFTRAG)) onWaehleAuftrag(wert.slice(WAHL_AUFTRAG.length));
    setAendern(false);
  }

  // Einrückung zählt nur die tatsächlich gezeigten Vorstufen.
  let tiefe = 0;
  const naechste = (): 0 | 1 | 2 => Math.min(tiefe++, 2) as 0 | 1 | 2;

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <h3 className="text-meta font-bold text-label3">Gehört zu</h3>
        {!leer && !aendern && (
          <span className="flex items-center gap-3">
            <button type="button" onClick={() => setAendern(true)} className="text-sekundaer font-medium text-tint-text hover:underline">
              Ändern
            </button>
            <button
              type="button"
              onClick={onEntfernen}
              title="Bezug entfernen"
              aria-label="Bezug entfernen"
              className="rounded-md p-1 text-label3 hover:bg-fill"
            >
              <X size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </span>
        )}
      </div>

      {!leer && (
        <div className="space-y-1.5">
          {kette.projekt && (
            <Zeile
              stufe={naechste()}
              icon={Folder}
              farbe="indigo"
              art="Projekt"
              titel={kette.projekt.name}
              ziel={linksAktiv && kette.projekt.id ? projektLink(kette.projekt.id) : null}
              navigate={navigate}
            />
          )}
          {kette.auftrag && (
            <Zeile
              stufe={naechste()}
              icon={Layers}
              farbe="blue"
              art="Auftrag"
              titel={kette.auftrag.titel}
              pille={
                kette.auftrag.status && (
                  <StatusPille status={auftragStatusZuToken(kette.auftrag.status)} label={AUFTRAG_STATUS_LABEL[kette.auftrag.status]} />
                )
              }
              ziel={linksAktiv && kette.auftrag.id ? auftragLink(kette.auftrag.id) : null}
              navigate={navigate}
            />
          )}
          {kette.vorgang && (
            <Zeile
              stufe={naechste()}
              icon={Rss}
              farbe="blue"
              art="Vorgang"
              titel={[kette.vorgang.nummer, kette.vorgang.titel].filter(Boolean).join(" · ")}
              pille={kette.vorgang.status && <VorgangStatusPille status={kette.vorgang.status} />}
              ziel={`/vorgaenge/${kette.vorgang.id}`}
              navigate={navigate}
            />
          )}
        </div>
      )}

      {kette.abweichung && (
        <p className="mt-1.5 text-sekundaer text-label2">Vorgang gehört zu Projekt {kette.abweichung}.</p>
      )}

      {(leer || aendern) && (
        <div className={leer ? "" : "mt-2"}>
          <SearchableSelect
            value=""
            onChange={gewaehlt}
            placeholder="Vorgang oder Auftrag suchen…"
            options={optionen}
            // Neuer Aufruf des Feldes: ohne Key bliebe der alte Suchtext stehen.
            key={aendern ? "aendern" : "leer"}
          />
          <div className="mt-1.5 flex items-center gap-3">
            {extraAktion}
            {aendern && (
              <button type="button" onClick={() => setAendern(false)} className="text-sekundaer font-medium text-label2 hover:text-label">
                Abbrechen
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
