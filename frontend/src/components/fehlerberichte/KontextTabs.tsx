import { ChevronDown, ChevronRight, MousePointerClick, Navigation, Send } from "lucide-react";
import { useState } from "react";

import type { Breadcrumb, FehlerberichtKontext, KonsolenEintrag, NetzwerkEintrag } from "../../bugreport/typen";
import { SegmentedControl } from "../apple/SegmentedControl";
import { netzwerkFehlgeschlagen } from "./darstellung";

type Tab = "klickpfad" | "netzwerk" | "konsole" | "umgebung";

function liste<T>(wert: unknown): T[] {
  return Array.isArray(wert) ? (wert as T[]) : [];
}

function objekt(wert: unknown): Record<string, unknown> {
  return wert && typeof wert === "object" && !Array.isArray(wert) ? (wert as Record<string, unknown>) : {};
}

function uhrzeit(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("de-DE", { timeZone: "Europe/Berlin" });
}

function Leer({ text }: { text: string }) {
  return <p className="py-4 text-sm text-label2">{text}</p>;
}

const MONO = "overflow-x-auto whitespace-pre-wrap break-all rounded-[var(--radius-ap-input)] bg-fill p-2 font-mono text-xs text-label";

const BREADCRUMB_ICON = { route: Navigation, klick: MousePointerClick, submit: Send } as const;

function Klickpfad({ eintraege }: { eintraege: Breadcrumb[] }) {
  if (eintraege.length === 0) return <Leer text="Kein Klickpfad mitgesendet." />;
  return (
    <ol className="space-y-3 py-2">
      {eintraege.map((b, i) => {
        const Icon = BREADCRUMB_ICON[b.typ] ?? MousePointerClick;
        return (
          <li key={i} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-fill text-label2">
              <Icon size={13} strokeWidth={2} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="break-all text-sm text-label">
                <span className="font-semibold">{b.typ}</span> · {b.ziel}
              </p>
              {b.text && <p className="break-words text-xs text-label2">{b.text}</p>}
              <p className="text-xs tabular-nums text-label2">{uhrzeit(b.zeit)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Kopfzeilen({ titel, werte }: { titel: string; werte?: Record<string, string> }) {
  if (!werte || Object.keys(werte).length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-label2">{titel}</p>
      <pre className={MONO}>{Object.entries(werte).map(([k, v]) => `${k}: ${v}`).join("\n")}</pre>
    </div>
  );
}

function Textblock({ titel, text }: { titel: string; text?: string }) {
  if (!text) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-label2">{titel}</p>
      <pre className={MONO}>{text}</pre>
    </div>
  );
}

function NetzwerkZeile({ e }: { e: NetzwerkEintrag }) {
  const [offen, setOffen] = useState(false);
  const fehl = netzwerkFehlgeschlagen(e);
  const Pfeil = offen ? ChevronDown : ChevronRight;
  return (
    <li data-fehlgeschlagen={fehl} className={fehl ? "bg-st-fehlt-bg" : ""}>
      <button
        type="button"
        aria-expanded={offen}
        onClick={() => setOffen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
      >
        <Pfeil size={14} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
        <span className="w-10 shrink-0 font-mono font-semibold text-label">{e.methode}</span>
        <span className="min-w-0 flex-1 break-all font-mono text-label">{e.url}</span>
        <span className={`shrink-0 font-mono font-semibold ${fehl ? "text-st-fehlt" : "text-label"}`}>
          {e.status || "–"}
        </span>
        <span className="hidden w-16 shrink-0 text-right tabular-nums text-label2 sm:inline">{e.dauer_ms} ms</span>
        <span className="hidden w-16 shrink-0 text-right tabular-nums text-label2 sm:inline">{uhrzeit(e.zeit)}</span>
      </button>
      {offen && (
        <div className="space-y-2 px-3 pb-3">
          {e.fehler && <p className="break-words text-xs font-semibold text-st-fehlt">Fehler: {e.fehler}</p>}
          <Kopfzeilen titel="Request-Header" werte={e.request_headers} />
          <Textblock titel="Request-Body" text={e.request_body} />
          <Kopfzeilen titel="Response-Header" werte={e.response_headers} />
          <Textblock titel="Response-Body" text={e.response_body} />
        </div>
      )}
    </li>
  );
}

function Netzwerk({ eintraege }: { eintraege: NetzwerkEintrag[] }) {
  if (eintraege.length === 0) return <Leer text="Keine Netzwerk-Requests mitgesendet." />;
  return (
    <ul className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
      {eintraege.map((e, i) => (
        <NetzwerkZeile key={i} e={e} />
      ))}
    </ul>
  );
}

const KONSOLE_KLASSE: Record<string, string> = {
  error: "text-st-fehlt bg-st-fehlt-bg",
  warn: "text-st-arbeit bg-st-arbeit-bg",
};

function KonsolenZeile({ e }: { e: KonsolenEintrag }) {
  const [offen, setOffen] = useState(false);
  return (
    <li data-level={e.level} className={KONSOLE_KLASSE[e.level] ?? "text-label"}>
      <div className="flex items-start gap-2 px-3 py-2 text-xs">
        <span className="w-12 shrink-0 font-mono font-semibold uppercase">{e.level}</span>
        <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono">{e.nachricht}</span>
        <span className="hidden shrink-0 tabular-nums sm:inline">{uhrzeit(e.zeit)}</span>
      </div>
      {e.stack && (
        <div className="px-3 pb-2">
          <button
            type="button"
            aria-expanded={offen}
            onClick={() => setOffen((v) => !v)}
            className="text-xs font-medium underline"
          >
            {offen ? "Stack ausblenden" : "Stack anzeigen"}
          </button>
          {offen && <pre className={`mt-1 ${MONO}`}>{e.stack}</pre>}
        </div>
      )}
    </li>
  );
}

function Konsole({ eintraege }: { eintraege: KonsolenEintrag[] }) {
  if (eintraege.length === 0) return <Leer text="Keine Konsolen-Einträge mitgesendet." />;
  return (
    <ul className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
      {eintraege.map((e, i) => (
        <KonsolenZeile key={i} e={e} />
      ))}
    </ul>
  );
}

function wertText(wert: unknown): string {
  if (typeof wert === "string") return wert;
  if (wert === null || wert === undefined) return "–";
  if (typeof wert === "object") return JSON.stringify(wert, null, 2);
  return String(wert);
}

function KeyValue({ titel, daten }: { titel: string; daten: Record<string, unknown> }) {
  const eintraege = Object.entries(daten);
  if (eintraege.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold text-label2 uppercase">{titel}</h3>
      <dl className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
        {eintraege.map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5 px-3 py-2 sm:flex-row sm:gap-3">
            <dt className="shrink-0 font-mono text-xs text-label2 sm:w-40">{k}</dt>
            <dd className="min-w-0 flex-1 whitespace-pre-wrap break-all font-mono text-xs text-label">{wertText(v)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Umgebung({ kontext }: { kontext: FehlerberichtKontext }) {
  const umgebung = objekt(kontext.umgebung);
  const sitzung = objekt(kontext.sitzung);
  const appState = objekt(kontext.app_state);
  if (!Object.keys(umgebung).length && !Object.keys(sitzung).length && !Object.keys(appState).length) {
    return <Leer text="Keine Umgebungsdaten mitgesendet." />;
  }
  return (
    <div className="space-y-4">
      <KeyValue titel="Umgebung" daten={umgebung} />
      <KeyValue titel="Sitzung" daten={sitzung} />
      <KeyValue titel="App-State" daten={appState} />
    </div>
  );
}

/** Jede Kategorie des Kontexts kann fehlen (der Melder waehlt aus, was
 * mitgeschickt wird) -- fehlende oder falsch typisierte Teile zeigen
 * einen Leerhinweis statt zu crashen. */
export function KontextTabs({ kontext }: { kontext: FehlerberichtKontext | null | undefined }) {
  const [tab, setTab] = useState<Tab>("klickpfad");
  const k = kontext ?? {};
  const breadcrumbs = liste<Breadcrumb>(k.breadcrumbs);
  const netzwerk = liste<NetzwerkEintrag>(k.netzwerk);
  const konsole = liste<KonsolenEintrag>(k.konsole);

  return (
    <div>
      <div className="mb-3 overflow-x-auto">
        <SegmentedControl<Tab>
          ariaLabel="Kontext"
          wert={tab}
          onChange={setTab}
          optionen={[
            { wert: "klickpfad", label: `Klickpfad (${breadcrumbs.length})` },
            { wert: "netzwerk", label: `Netzwerk (${netzwerk.length})` },
            { wert: "konsole", label: `Konsole (${konsole.length})` },
            { wert: "umgebung", label: "Umgebung" },
          ]}
        />
      </div>
      {tab === "klickpfad" && <Klickpfad eintraege={breadcrumbs} />}
      {tab === "netzwerk" && <Netzwerk eintraege={netzwerk} />}
      {tab === "konsole" && <Konsole eintraege={konsole} />}
      {tab === "umgebung" && <Umgebung kontext={k} />}
    </div>
  );
}
