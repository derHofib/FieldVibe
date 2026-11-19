import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Star, UserMinus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { kundenApi } from "../../api/endpoints";
import { Monogramm } from "../../components/apple/Monogramm";
import { SearchField } from "../../components/apple/SearchField";
import { useToast } from "../../components/Toast";
import type { BetreuerKandidat, Kunde, KundeBetreuungSammelAktion } from "../../types";
import { Karte } from "../OfficeUi";

type Modus = KundeBetreuungSammelAktion;

interface Person {
  id: string;
  name: string;
  untertitel: string;
  nurBetreuteKunden: boolean;
  anzahl: number;
}

const MODUS_LABEL: Record<Modus, string> = {
  hinzufuegen: "Betreuer hinzufügen",
  hauptbetreuer: "Hauptbetreuer setzen",
  entfernen: "Betreuer entfernen",
};

function kundenText(n: number): string {
  return n === 1 ? "1 Kunde" : `${n} Kunden`;
}

/** Fußzeile des Menüs: beschreibt die Wirkung für die Person unter dem Zeiger. */
export function wirkungsText(modus: Modus, name: string, anzahl: number, opts: { auchHaupt: boolean; betroffen: number }): string {
  if (modus === "hinzufuegen") {
    return `Fügt ${name} bei ${kundenText(anzahl)} hinzu. Bestehende Betreuer bleiben.${
      opts.auchHaupt ? " Wo noch kein Hauptbetreuer festgelegt ist, wird die Person Hauptbetreuer." : ""
    }`;
  }
  if (modus === "hauptbetreuer") {
    return `Setzt ${name} bei ${kundenText(anzahl)} als Hauptbetreuer. Ein bisheriger Hauptbetreuer bleibt als Vertretung.`;
  }
  return `Entfernt ${name} bei ${opts.betroffen} von ${kundenText(anzahl)}.`;
}

function toastText(modus: Modus, name: string, n: number): string {
  if (modus === "hinzufuegen") return `${name} bei ${kundenText(n)} hinzugefügt`;
  if (modus === "hauptbetreuer") return `${name} ist bei ${kundenText(n)} jetzt Hauptbetreuer`;
  return `${name} bei ${kundenText(n)} entfernt`;
}

/** Aktionsleiste der Mehrfachauswahl; ersetzt die Filterzeile, solange Kunden gewählt sind. */
export function KundenSammelleiste({
  ausgewaehlt,
  kandidaten,
  onLeeren,
}: {
  ausgewaehlt: Kunde[];
  kandidaten: BetreuerKandidat[] | undefined;
  onLeeren: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [modus, setModus] = useState<Modus | null>(null);
  const [suche, setSuche] = useState("");
  const [vorschau, setVorschau] = useState<string | null>(null);
  const [auchHaupt, setAuchHaupt] = useState(true);
  const wurzel = useRef<HTMLDivElement>(null);

  const personen: Person[] = useMemo(() => {
    const info = (k: BetreuerKandidat): Person => ({
      id: k.user_id,
      name: k.name,
      untertitel: [k.account_typ_name, k.nur_betreute_kunden ? "sieht nur betreute Kunden" : "sieht alle Kunden"]
        .filter(Boolean)
        .join(" · "),
      nurBetreuteKunden: k.nur_betreute_kunden,
      anzahl: k.anzahl_kunden,
    });
    if (modus !== "entfernen") return (kandidaten ?? []).filter((k) => k.aktiv).map(info);
    // Entfernen: nur, wer bei mindestens einem gewählten Kunden Betreuer ist (auch Deaktivierte).
    const imAuswahl = new Map<string, string>();
    for (const k of ausgewaehlt) for (const b of k.betreuung ?? []) imAuswahl.set(b.user_id, b.name);
    return [...imAuswahl.entries()].map(([id, name]) => {
      const k = (kandidaten ?? []).find((x) => x.user_id === id);
      return k ? info(k) : { id, name, untertitel: "", nurBetreuteKunden: false, anzahl: 0 };
    });
  }, [kandidaten, modus, ausgewaehlt]);

  const sichtbar = personen
    .filter((p) => p.name.toLowerCase().includes(suche.trim().toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name, "de"));

  const schliessen = () => {
    setModus(null);
    setSuche("");
    setVorschau(null);
  };

  useEffect(() => {
    if (!modus) return;
    const aufKlick = (e: MouseEvent) => {
      if (wurzel.current && !wurzel.current.contains(e.target as Node)) schliessen();
    };
    document.addEventListener("mousedown", aufKlick);
    return () => document.removeEventListener("mousedown", aufKlick);
  }, [modus]);

  const anwenden = useMutation({
    mutationFn: (v: { person: Person; modus: Modus }) =>
      kundenApi.betreuungSammel({
        kunde_ids: ausgewaehlt.map((k) => k.id),
        aktion: v.modus,
        user_id: v.person.id,
        ...(v.modus === "hinzufuegen" ? { auch_hauptbetreuer: auchHaupt } : {}),
      }),
    onSuccess: (res, v) => {
      toast.erfolg(toastText(v.modus, v.person.name, res.geaendert));
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      queryClient.invalidateQueries({ queryKey: ["kunde-profil"] });
      schliessen();
      onLeeren();
    },
  });

  const aktiv = vorschau ? personen.find((p) => p.id === vorschau) : undefined;
  const betroffen = aktiv ? ausgewaehlt.filter((k) => k.betreuung?.some((b) => b.user_id === aktiv.id)).length : 0;

  const knopf = (m: Modus, icon: ReactNode) => (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-expanded={modus === m}
      onClick={() => {
        setSuche("");
        setVorschau(null);
        setModus(modus === m ? null : m);
      }}
      className="btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sekundaer font-semibold"
      style={modus === m ? { borderColor: "var(--tint)" } : undefined}
    >
      {icon}
      {MODUS_LABEL[m]}
    </button>
  );

  return (
    <Karte className="mb-4 px-3 py-2" style={{ borderColor: "var(--tint)", borderWidth: 1.5 }}>
      <div ref={wurzel} className="relative flex flex-wrap items-center gap-2">
        <span className="pr-2 text-fliess font-semibold text-label" aria-live="polite">
          {kundenText(ausgewaehlt.length)} ausgewählt
        </span>
        {knopf("hinzufuegen", <Plus size={15} strokeWidth={2} aria-hidden="true" />)}
        {knopf("hauptbetreuer", <Star size={15} strokeWidth={2} aria-hidden="true" />)}
        {knopf("entfernen", <UserMinus size={15} strokeWidth={2} aria-hidden="true" />)}
        <button type="button" onClick={onLeeren} className="ml-auto text-sekundaer font-semibold text-tint-text">
          Auswahl aufheben
        </button>

        {modus && (
          <div
            role="dialog"
            aria-label={MODUS_LABEL[modus]}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.stopPropagation();
                schliessen();
              }
            }}
            className="absolute top-full left-0 z-30 mt-2 w-[380px] max-w-full rounded-[var(--radius-ap-md)] border-[0.5px] border-sepstrong p-1.5"
            style={{ backgroundColor: "var(--menu)", boxShadow: "0 10px 30px rgba(0,0,0,.22)" }}
          >
            <SearchField value={suche} onChange={setSuche} placeholder="Mitarbeiter suchen…" ariaLabel="Mitarbeiter suchen" autoFocus />
            <ul className="mt-1 max-h-72 overflow-y-auto">
              {sichtbar.length === 0 && (
                <li className="px-2 py-3 text-sekundaer text-label2">
                  {modus === "entfernen" ? "Bei den gewählten Kunden ist niemand Betreuer." : "Keine Mitarbeiter gefunden."}
                </li>
              )}
              {sichtbar.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    disabled={anwenden.isPending}
                    onClick={() => anwenden.mutate({ person: p, modus })}
                    onMouseEnter={() => setVorschau(p.id)}
                    onFocus={() => setVorschau(p.id)}
                    className="group flex w-full items-center gap-2 rounded-[6px] px-2 py-1.5 text-left hover:bg-tint-solid hover:text-white focus-visible:bg-tint-solid focus-visible:text-white focus-visible:outline-none disabled:opacity-50"
                  >
                    <Monogramm name={p.name} groesse={28} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-fliess text-label group-hover:text-white group-focus-visible:text-white">{p.name}</span>
                      {p.untertitel && (
                        <span className="block truncate text-meta text-label2 group-hover:text-white/80 group-focus-visible:text-white/80">
                          {p.untertitel}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-sekundaer text-label2 group-hover:text-white/80 group-focus-visible:text-white/80">
                      {kundenText(p.anzahl)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {modus === "hinzufuegen" && (
              <label className="mt-1 flex cursor-pointer items-center gap-2 border-t border-sep px-2 py-2 text-sekundaer text-label">
                <input
                  type="checkbox"
                  checked={auchHaupt}
                  onChange={(e) => setAuchHaupt(e.target.checked)}
                  className="sr-only"
                />
                <span
                  aria-hidden="true"
                  className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full"
                  style={{
                    border: auchHaupt ? "none" : "1.5px solid var(--label3)",
                    backgroundColor: auchHaupt ? "var(--tint)" : "transparent",
                  }}
                >
                  {auchHaupt && <Check size={12} strokeWidth={3} className="text-white" />}
                </span>
                <span>
                  Gleich als Hauptbetreuer setzen,
                  <span className="block text-label2">wo noch keiner festgelegt ist</span>
                </span>
              </label>
            )}
            {modus === "entfernen" && aktiv?.nurBetreuteKunden && (
              <p role="alert" className="mx-1 mt-1 rounded-[6px] bg-st-arbeit-bg px-2 py-1.5 text-sekundaer text-st-arbeit">
                {aktiv.name} sieht nur betreute Kunden und sieht diese Kunden und ihre Vorgänge danach nicht mehr.
              </p>
            )}
            <p className="border-t border-sep px-2 py-2 text-sekundaer text-label2">
              {aktiv
                ? wirkungsText(modus, aktiv.name, ausgewaehlt.length, { auchHaupt, betroffen })
                : `Wähle eine Person – die Änderung gilt für ${kundenText(ausgewaehlt.length)}.`}
            </p>
          </div>
        )}
      </div>
    </Karte>
  );
}
