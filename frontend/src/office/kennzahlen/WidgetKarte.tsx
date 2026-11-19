import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Lock, SearchX, Table2, X, BarChart3, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { kennzahlenApi } from "../../api/endpoints";
import { AktionsMenue, type AktionsMenueEintrag } from "../../components/AktionsMenue";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Skeleton } from "../../components/Skeleton";
import type { DashboardWidget, DashboardZeitraum, KennzahlDaten, KennzahlDef, WidgetGroesse } from "../../types/kennzahlen";
import { Karte } from "../OfficeUi";
import { DIAGRAMM_DARSTELLUNGEN, passendeGruppierung } from "./darstellungen";
import { Balken } from "./darstellungen/Balken";
import type { DarstellungProps } from "./darstellungen/gemeinsam";
import { Linie } from "./darstellungen/Linie";
import { Ring } from "./darstellungen/Ring";
import { Saeulen } from "./darstellungen/Saeulen";
import { Tabelle } from "./darstellungen/Tabelle";
import { Zahl } from "./darstellungen/Zahl";
import { ZahlVerlauf } from "./darstellungen/ZahlVerlauf";
import { type BerechneterZeitraum, zeitGruppierungFuer } from "./zeitraum";

const GROESSEN: WidgetGroesse[] = ["s", "m", "l", "xl"];

export interface WidgetKarteProps {
  widget: DashboardWidget;
  /** null = Kennzahl steht nicht im Katalog des Nutzers (z. B. geteiltes Dashboard mit Finanz-Widget). */
  def: KennzahlDef | null;
  zeitraumArt: DashboardZeitraum;
  zeitraum: BerechneterZeitraum;
  bearbeiten: boolean;
  ausgewaehlt: boolean;
  onAuswaehlen: () => void;
  onGroesse: (groesse: WidgetGroesse) => void;
  onEntfernen: () => void;
  /** "Darstellung ändern" im Menü: startet das Bearbeiten und öffnet die Einstellungen dieses Widgets. */
  onDarstellungAendern: () => void;
  /** Ziehgriff (nur im Bearbeiten-Modus), kommt vom Raster. */
  griff: ReactNode;
}

function istStatusKennzahl(widget: DashboardWidget, gruppierung: string): boolean {
  return widget.kennzahl.startsWith("vorgaenge.") && gruppierung === "status";
}

/** Eine Kennzahl als Karte. Holt ihre Daten selbst (eine Abfrage je Widget): Der Query-Schlüssel enthält den Zeitraum,
 * ein Zeitraumwechsel lädt deshalb nur neu, was sich ändert -- Momentaufnahmen ("Stand heute") bleiben stehen. */
export function WidgetKarte({
  widget,
  def,
  zeitraumArt,
  zeitraum,
  bearbeiten,
  ausgewaehlt,
  onAuswaehlen,
  onGroesse,
  onEntfernen,
  onDarstellungAendern,
  griff,
}: WidgetKarteProps) {
  // Lokaler Umschalter "Als Tabelle", bewusst nicht gespeichert: Er dient dem Nachlesen genauer Werte.
  const [alsTabelle, setAlsTabelle] = useState(false);
  const istDiagramm = DIAGRAMM_DARSTELLUNGEN.includes(widget.darstellung);
  const anzeige = alsTabelle && istDiagramm ? "tabelle" : widget.darstellung;

  const stand = def?.art === "stand";
  const zeitGruppe = def ? zeitGruppierungFuer(zeitraumArt, def.gruppierungen) : null;
  let gruppierung = "gesamt";
  if (widget.darstellung === "zahl_verlauf") {
    // Verlauf läuft immer über die Zeitachse, unabhängig von der gewählten Aufteilung; fehlt sie, bleibt die Zahl.
    gruppierung = zeitGruppe ?? "gesamt";
  } else if (widget.darstellung !== "zahl") {
    gruppierung = widget.gruppierung ?? (def ? passendeGruppierung(def, anzeige, null) : null) ?? "gesamt";
  }
  // Nur senden, was die Kennzahl auswertet: Momentaufnahmen haben weder Zeitraum noch Vorperiode.
  const mitZeitraum = !stand;
  const vergleichen = widget.vergleich && !stand;
  const von = mitZeitraum ? zeitraum.von : undefined;
  const bis = mitZeitraum ? zeitraum.bis : undefined;
  const vergleichVon = vergleichen ? zeitraum.vergleich_von : undefined;
  const vergleichBis = vergleichen ? zeitraum.vergleich_bis : undefined;

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["kennzahl-daten", widget.kennzahl, gruppierung, von, bis, vergleichVon, vergleichBis],
    queryFn: () =>
      kennzahlenApi.daten({
        kennzahl: widget.kennzahl,
        gruppierung,
        von,
        bis,
        vergleich_von: vergleichVon,
        vergleich_bis: vergleichBis,
      }),
    // Kein Recht / unbekannte Kennzahl ändert sich durch Wiederholen nicht.
    retry: (anzahl, fehler) => !(fehler instanceof ApiError && (fehler.status === 403 || fehler.status === 404)) && anzahl < 2,
  });

  const grundTitel = widget.titel || def?.titel || widget.kennzahl;
  const gruppierungLabel = def?.gruppierungen.find((g) => g.schluessel === gruppierung)?.label;
  const titel =
    !widget.titel && widget.darstellung !== "zahl" && widget.darstellung !== "zahl_verlauf" && gruppierungLabel
      ? `${grundTitel} nach ${gruppierungLabel}`
      : grundTitel;

  const einzeilig = anzeige === "zahl" || anzeige === "zahl_verlauf";
  const hoehe = einzeilig ? "min-h-[132px]" : "min-h-[300px]";

  const menue: (AktionsMenueEintrag | "trenner")[] = [
    ...(istDiagramm
      ? [
          alsTabelle
            ? { label: "Als Diagramm", icon: BarChart3, onClick: () => setAlsTabelle(false) }
            : { label: "Als Tabelle", icon: Table2, onClick: () => setAlsTabelle(true) },
        ]
      : []),
    { label: "Darstellung ändern", icon: SlidersHorizontal, onClick: onDarstellungAendern },
  ];

  return (
    <Karte
      className={`flex h-full flex-col gap-3 p-4 ${bearbeiten ? "cursor-pointer" : ""}`}
      // Auswahlrand inline: .card-ap setzt den Rand außerhalb der Cascade-Layer, eine Tailwind-Klasse würde ignoriert.
      style={ausgewaehlt ? { borderColor: "var(--tint)", boxShadow: "0 0 0 1px var(--tint)" } : undefined}
    >
      {/* Klick auf die Karte wählt im Bearbeiten-Modus das Widget aus; per Tastatur über den Titel-Button. */}
      <div className="flex items-center gap-2" onClick={bearbeiten ? onAuswaehlen : undefined}>
        {bearbeiten && griff}
        {bearbeiten ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAuswaehlen();
            }}
            aria-pressed={ausgewaehlt}
            aria-label={`${titel} bearbeiten`}
            className="min-w-0 flex-1 truncate text-left text-fliess font-semibold text-label2"
          >
            {titel}
          </button>
        ) : (
          <h2 className="min-w-0 flex-1 truncate text-fliess font-semibold text-label2" title={titel}>
            {titel}
          </h2>
        )}
        {stand && <span className="shrink-0 text-meta text-label2">Stand heute</span>}
        {bearbeiten ? (
          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <AktionsMenue
              label={`Größe von ${titel} ändern`}
              eintraege={GROESSEN.map((g) => ({
                label: g.toUpperCase(),
                aktiv: g === widget.groesse,
                onClick: () => onGroesse(g),
              }))}
              ausloeser={() => (
                <span className="inline-flex items-center gap-0.5 rounded-md bg-fill px-1.5 py-0.5 text-meta font-semibold text-label">
                  {widget.groesse.toUpperCase()}
                  <ChevronDown size={11} strokeWidth={2.5} aria-hidden="true" />
                </span>
              )}
            />
            <button
              type="button"
              onClick={onEntfernen}
              aria-label={`${titel} entfernen`}
              title="Entfernen"
              className="btn-ap-toolbar"
            >
              <X size={15} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
        ) : (
          <div className="shrink-0">
            <AktionsMenue label={`Aktionen für ${titel}`} eintraege={menue} />
          </div>
        )}
      </div>

      <div className={`flex flex-1 flex-col ${hoehe}`} onClick={bearbeiten ? onAuswaehlen : undefined}>
        <Inhalt
          isLoading={isLoading}
          fehler={error}
          onErneut={() => void refetch()}
          daten={data}
          darstellung={anzeige}
          groesse={widget.groesse}
          vergleich={vergleichen}
          statusFarben={istStatusKennzahl(widget, gruppierung)}
          summierbar={def?.summierbar ?? false}
          titel={titel}
          vorLabel={zeitraum.vorperiodeLabel}
          stand={stand}
        />
      </div>
    </Karte>
  );
}

function Inhalt({
  isLoading,
  fehler,
  onErneut,
  daten,
  darstellung,
  stand,
  ...rest
}: Omit<DarstellungProps, "daten"> & {
  isLoading: boolean;
  fehler: unknown;
  onErneut: () => void;
  daten: KennzahlDaten | undefined;
  darstellung: DashboardWidget["darstellung"];
  stand: boolean;
}) {
  if (isLoading) {
    return (
      <div role="status" aria-busy="true" className="flex flex-1 flex-col gap-2">
        <span className="sr-only">Lädt…</span>
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="min-h-8 flex-1" />
      </div>
    );
  }
  if (fehler) {
    if (fehler instanceof ApiError && fehler.status === 403) {
      return <EmptyState icon={Lock} text="Keine Berechtigung für diese Kennzahl" className="py-3!" />;
    }
    if (fehler instanceof ApiError && fehler.status === 404) {
      return <EmptyState icon={SearchX} text="Kennzahl nicht mehr verfügbar" className="py-3!" />;
    }
    return <FehlerZustand fehler={fehler} was="Die Kennzahl" onErneut={onErneut} className="[&>div]:py-3" />;
  }
  if (!daten) return null;

  const keineDaten =
    darstellung === "zahl" || darstellung === "zahl_verlauf"
      ? daten.gesamt === null && daten.zeilen.every((z) => z.wert === null)
      : daten.zeilen.length === 0 || daten.zeilen.every((z) => z.wert === null);
  if (keineDaten) {
    return <EmptyState icon={SearchX} text={stand ? "Keine Daten" : "Im Zeitraum keine Daten"} className="py-3!" />;
  }

  const props: DarstellungProps = { daten, ...rest };
  switch (darstellung) {
    case "zahl":
      return <Zahl daten={daten} vergleich={rest.vergleich} vorLabel={rest.vorLabel} />;
    case "zahl_verlauf":
      return <ZahlVerlauf {...props} />;
    case "saeulen":
      return <Saeulen {...props} />;
    case "linie":
      return <Linie {...props} />;
    case "balken":
      return <Balken {...props} />;
    case "ring":
      return <Ring {...props} />;
    case "tabelle":
      return <Tabelle {...props} />;
  }
}
