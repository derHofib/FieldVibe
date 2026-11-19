import {
  ArrowLeft,
  BarChart3,
  BarChartHorizontal,
  Hash,
  LineChart,
  PieChart,
  Table2,
  Trash2,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useId } from "react";

import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { Select } from "../../components/apple/Select";
import { Switch } from "../../components/apple/Switch";
import type { Darstellung, DashboardWidget, KennzahlDef, WidgetGroesse } from "../../types/kennzahlen";
import {
  DARSTELLUNG_LABEL,
  DARSTELLUNG_REIHENFOLGE,
  erlaubteDarstellungen,
  gruppierungenFuer,
  passendeGruppierung,
} from "./darstellungen";
import { BearbeitenSpalte } from "./KatalogPanel";

const ICON: Record<Darstellung, LucideIcon> = {
  zahl: Hash,
  zahl_verlauf: TrendingUp,
  saeulen: BarChart3,
  linie: LineChart,
  balken: BarChartHorizontal,
  ring: PieChart,
  tabelle: Table2,
};

const GROESSEN: { wert: WidgetGroesse; label: string }[] = [
  { wert: "s", label: "S" },
  { wert: "m", label: "M" },
  { wert: "l", label: "L" },
  { wert: "xl", label: "XL" },
];

// Server-Grenze für Widget-Titel (DashboardWidget.titel).
const TITEL_MAX = 80;

function Abschnitt({ titel, children }: { titel: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2 px-4 py-3">
      <h3 className="text-meta font-semibold tracking-wide text-label2 uppercase">{titel}</h3>
      {children}
    </section>
  );
}

/** Ersetzt den Katalog, solange ein Widget ausgewählt ist. Jede Änderung wirkt sofort im Raster, dort aktualisiert
 * sich das Widget -- eine eigene Vorschau ist deshalb nicht nötig. */
export function WidgetEinstellungen({
  widget,
  def,
  onAendern,
  onZurueck,
  onEntfernen,
}: {
  widget: DashboardWidget;
  /** null = Kennzahl nicht im Katalog (nur noch Größe, Titel und Entfernen sind sinnvoll). */
  def: KennzahlDef | null;
  onAendern: (aenderung: Partial<DashboardWidget>) => void;
  onZurueck: () => void;
  onEntfernen: () => void;
}) {
  const titelId = useId();
  const aufteilenId = useId();
  const erlaubt = def ? erlaubteDarstellungen(def) : [];
  const gruppierungen = def ? gruppierungenFuer(def, widget.darstellung) : [];
  const titel = widget.titel || def?.titel || widget.kennzahl;

  function darstellungWaehlen(darstellung: Darstellung) {
    if (!def) return;
    onAendern({ darstellung, gruppierung: passendeGruppierung(def, darstellung, widget.gruppierung) });
  }

  return (
    <BearbeitenSpalte
      titel="Widget-Einstellungen"
      kopf={
        <div className="border-b-[0.5px] border-sep px-4 py-3">
          <button
            type="button"
            onClick={onZurueck}
            className="mb-1 inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text"
          >
            <ArrowLeft size={14} strokeWidth={2} aria-hidden="true" /> Zurück zum Katalog
          </button>
          <h2 className="truncate text-zeile font-semibold text-label">{titel}</h2>
        </div>
      }
    >
      <div className="divide-y-[0.5px] divide-sep">
        <Abschnitt titel="Darstellung">
          <div role="group" aria-label="Darstellung" className="grid grid-cols-4 gap-2">
            {DARSTELLUNG_REIHENFOLGE.map((darstellung) => {
              const Icon = ICON[darstellung];
              const aktiv = widget.darstellung === darstellung;
              const moeglich = erlaubt.includes(darstellung);
              return (
                <button
                  key={darstellung}
                  type="button"
                  disabled={!moeglich}
                  aria-pressed={aktiv}
                  onClick={() => darstellungWaehlen(darstellung)}
                  // Bewusst kein .btn-ap: feste 28px Höhe, die ein Symbol mit Beschriftung darunter sprengt.
                  className={`flex flex-col items-center gap-1 rounded-[var(--radius-ap-sm)] border px-1 py-2 text-meta font-medium text-label transition-colors enabled:hover:bg-fill disabled:cursor-not-allowed disabled:opacity-40 ${
                    aktiv ? "border-tint bg-tintbg" : "border-sep bg-card"
                  }`}
                >
                  <Icon size={18} strokeWidth={2} aria-hidden="true" />
                  <span className="text-center leading-tight">{DARSTELLUNG_LABEL[darstellung]}</span>
                </button>
              );
            })}
          </div>
        </Abschnitt>

        <Abschnitt titel="Aufteilen nach">
          <Select
            id={aufteilenId}
            aria-label="Aufteilen nach"
            value={widget.gruppierung ?? "gesamt"}
            disabled={gruppierungen.length === 0}
            onChange={(e) => onAendern({ gruppierung: e.target.value })}
          >
            {gruppierungen.length === 0 && <option value="gesamt">Gesamt</option>}
            {gruppierungen.map((g) => (
              <option key={g.schluessel} value={g.schluessel}>
                {g.label}
              </option>
            ))}
          </Select>
          {gruppierungen.length === 0 && (
            <p className="text-sekundaer text-label2">Diese Darstellung zeigt den Gesamtwert.</p>
          )}
        </Abschnitt>

        <Abschnitt titel="Größe">
          <SegmentedControl<WidgetGroesse>
            ariaLabel="Größe"
            optionen={GROESSEN}
            wert={widget.groesse}
            onChange={(groesse) => onAendern({ groesse })}
            volleBreite
          />
        </Abschnitt>

        <Abschnitt titel="Titel">
          <input
            id={titelId}
            aria-label="Titel"
            type="text"
            value={widget.titel ?? ""}
            maxLength={TITEL_MAX}
            placeholder={def?.titel ?? widget.kennzahl}
            onChange={(e) => onAendern({ titel: e.target.value === "" ? null : e.target.value })}
            className="field-ap"
          />
        </Abschnitt>

        {def?.art === "zeitraum" && (
          <Abschnitt titel="Vergleich">
            <div className="flex items-center justify-between gap-3">
              <span className="text-fliess text-label">
                Mit Vorperiode vergleichen
              </span>
              <Switch
                checked={widget.vergleich}
                onChange={(vergleich) => onAendern({ vergleich })}
                ariaLabel="Mit Vorperiode vergleichen"
              />
            </div>
          </Abschnitt>
        )}

        <div className="px-4 py-3">
          <button
            type="button"
            onClick={onEntfernen}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-fliess font-medium text-st-fehlt hover:bg-st-fehlt-bg"
          >
            <Trash2 size={15} strokeWidth={2} aria-hidden="true" /> Entfernen
          </button>
        </div>
      </div>
    </BearbeitenSpalte>
  );
}
