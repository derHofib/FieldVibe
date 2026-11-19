import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Search, SearchX } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { tagsApi } from "../../api/endpoints";
import { sichtbareNavSeiten } from "../../config/navSeiten";
import { useAuth } from "../../context/AuthContext";
import { EmptyState } from "../EmptyState";
import { FehlerZustand } from "../FehlerZustand";
import { SkeletonList } from "../Skeleton";
import {
  erlaubteKategorien,
  formatAnzahl,
  KATEGORIE_INFO,
  kategorienLeiste,
  listenPfad,
  seiteZuEintrag,
  type SucheEintrag,
  trefferZuEintrag,
  verlaufZuEintrag,
} from "./kategorien";
import { NachladenAnker } from "./NachladenAnker";
import { SuchFilterLeiste } from "./SuchFilterLeiste";
import { Taste, TrefferZeile } from "./TrefferZeile";
import { useGlobaleSuche } from "./useGlobaleSuche";
import { merkeZuletzt, useZuletztGeoeffnet } from "./zuletztGeoeffnet";

const MAX_SEITEN = 5;

interface Abschnitt {
  key: string;
  titel: string;
  /** Anzahl hinter dem Titel („KUNDEN · 3"). */
  zahl?: string;
  eintraege: SucheEintrag[];
  rechts?: ReactNode;
}

const MAC = typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform);

/** Schwebendes Suchfenster über der aktuellen Seite (Office). Zustand lebt nur, solange es offen ist --
 * beim Schließen sind Eingabe und Filter damit zurückgesetzt. */
export function GlobaleSuche({ anfang, onSchliessen }: { anfang: string; onSchliessen: () => void }) {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const suche = useGlobaleSuche(anfang);
  const { eintraege: zuletzt, leeren } = useZuletztGeoeffnet();
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const listeId = useId();
  const eingabeRef = useRef<HTMLInputElement>(null);
  const [auswahl, setAuswahl] = useState(0);

  const { eingabe, setEingabe, begriff, aktiv, kategorie, setKategorie, nurOffen } = suche;
  const hatEingabe = eingabe.trim().length > 0;

  // Fokus ins Suchfeld und beim Schließen zurück; Seite dahinter nicht scrollen.
  useEffect(() => {
    const vorher = document.activeElement as HTMLElement | null;
    eingabeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      vorher?.focus?.();
    };
  }, []);

  useEffect(() => {
    const beiTaste = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) {
        e.preventDefault();
        onSchliessen();
      }
    };
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
  }, [onSchliessen]);

  const seiten = useMemo(() => {
    const alle = sichtbareNavSeiten(currentUser, hatRecht, "office");
    const q = eingabe.trim().toLowerCase();
    if (q.startsWith("#")) return [];
    // Mit einer gewählten Kategorie wären Seiten zwischen den Treffern fehl am Platz.
    if (q && kategorie !== "alle") return [];
    return (q ? alle.filter((s) => s.label.toLowerCase().includes(q)) : alle).slice(0, MAX_SEITEN).map(seiteZuEintrag);
  }, [currentUser, hatRecht, eingabe, kategorie]);

  const abschnitte = useMemo<Abschnitt[]>(() => {
    if (!hatEingabe) {
      const verlauf = zuletzt.map((e) => verlaufZuEintrag(e, "office")).filter((e): e is SucheEintrag => !!e);
      return [
        ...(verlauf.length > 0
          ? [
              {
                key: "zuletzt",
                titel: "Zuletzt geöffnet",
                eintraege: verlauf,
                rechts: (
                  <button
                    type="button"
                    tabIndex={-1}
                    aria-hidden="true"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={leeren}
                    className="font-medium tracking-normal text-tint-text normal-case"
                  >
                    Verlauf leeren
                  </button>
                ),
              },
            ]
          : []),
        ...(seiten.length > 0 ? [{ key: "seiten", titel: "Springen zu", eintraege: seiten }] : []),
      ];
    }
    const treffer: Abschnitt[] = suche.gruppen.map((g) => {
      const n = suche.anzahl?.[g.kategorie];
      const plural = KATEGORIE_INFO[g.kategorie].plural;
      const liste = listenPfad(g.kategorie, begriff, nurOffen);
      return {
        key: g.kategorie,
        titel: plural,
        zahl: n !== undefined ? formatAnzahl(n) : undefined,
        eintraege: g.treffer.map((t) => trefferZuEintrag(t, "office")).filter((e): e is SucheEintrag => !!e),
        rechts:
          kategorie === "alle" && n !== undefined && g.kategorie !== "tag" ? (
            <button
              type="button"
              tabIndex={-1}
              aria-hidden="true"
              onMouseDown={(e) => e.preventDefault()}
              // Ohne eigene Liste (Anlagen) zeigt das Fenster die Kategorie vollständig.
              onClick={() => (liste ? oeffneListe(liste) : setKategorie(g.kategorie))}
              className="font-medium tracking-normal text-tint-text normal-case"
            >
              Alle {formatAnzahl(n)} in {plural}
            </button>
          ) : undefined,
      };
    });
    return [...(seiten.length > 0 ? [{ key: "seiten", titel: "Seiten", eintraege: seiten }] : []), ...treffer];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hatEingabe, zuletzt, seiten, suche.gruppen, suche.anzahl, kategorie, begriff, nurOffen, leeren]);

  const zeilen = useMemo(() => abschnitte.flatMap((a) => a.eintraege), [abschnitte]);
  const gewaehlt = Math.min(auswahl, Math.max(zeilen.length - 1, 0));

  useEffect(() => {
    setAuswahl(0);
  }, [begriff, kategorie, nurOffen, suche.zeitraum, suche.mirZugewiesen, hatEingabe]);

  useEffect(() => {
    document.getElementById(`${listeId}-opt-${gewaehlt}`)?.scrollIntoView?.({ block: "nearest" });
  }, [gewaehlt, listeId]);

  function oeffneListe(pfad: string) {
    navigate(pfad);
    onSchliessen();
  }

  function oeffnen(eintrag: SucheEintrag, neuerTab: boolean) {
    if ("tag" in eintrag.ziel) {
      setEingabe(`#${eintrag.ziel.tag}`);
      eingabeRef.current?.focus();
      return;
    }
    if (eintrag.kategorie !== "seite" && currentUser) {
      merkeZuletzt(currentUser.id, {
        kategorie: eintrag.kategorie,
        id: eintrag.id,
        titel: eintrag.titel,
        untertitel: eintrag.untertitel,
        status: eintrag.statusRoh,
      });
    }
    if (neuerTab) {
      window.open(eintrag.ziel.pfad, "_blank", "noopener");
      return;
    }
    navigate(eintrag.ziel.pfad);
    onSchliessen();
  }

  function wechselKategorie(richtung: 1 | -1) {
    const erlaubt = erlaubteKategorien(suche.anzahl, currentUser, hatRecht, "office");
    const leiste = kategorienLeiste({ anzahl: suche.anzahl, erlaubt, gewaehlt: kategorie });
    const reihe = ["alle" as const, ...leiste.sichtbar, ...leiste.mehr];
    const i = reihe.indexOf(kategorie);
    setKategorie(reihe[(i + richtung + reihe.length) % reihe.length]);
  }

  function beiTaste(e: KeyboardEvent<HTMLDivElement>) {
    const ziel = e.target as HTMLElement;
    // Menüs (Zeitraum, Mehr) bringen ihre eigene Tastatursteuerung mit.
    if (ziel.closest('[role="menu"]')) return;
    const imFeld = ziel === eingabeRef.current;
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && (imFeld || ziel.tagName === "BUTTON")) {
      e.preventDefault();
      setAuswahl(e.key === "ArrowDown" ? Math.min(gewaehlt + 1, zeilen.length - 1) : Math.max(gewaehlt - 1, 0));
    } else if (e.key === "Enter" && imFeld) {
      e.preventDefault();
      const eintrag = zeilen[gewaehlt];
      if (eintrag) oeffnen(eintrag, e.metaKey || e.ctrlKey);
    } else if (e.key === "Tab" && imFeld) {
      e.preventDefault();
      wechselKategorie(e.shiftKey ? -1 : 1);
    }
  }

  const erlaubt = erlaubteKategorien(suche.anzahl, currentUser, hatRecht, "office");
  const wartetAufTreffer = hatEingabe && (!aktiv || suche.laedt);
  const keineTreffer = hatEingabe && !wartetAufTreffer && zeilen.length === 0 && !suche.fehler;
  let offset = 0;

  return createPortal(
    <div
      className="suche-scrim fixed inset-0 z-50 flex items-start justify-center px-6 pt-[11vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onSchliessen();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Globale Suche"
        onKeyDown={beiTaste}
        className="glas-flaeche suche-fenster-ein flex max-h-[74vh] w-[880px] max-w-[calc(100vw-48px)] flex-col overflow-hidden rounded-[16px] text-label"
      >
        <div className="flex items-center gap-3 px-[18px] pt-4 pb-3">
          <Search size={22} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
          <input
            ref={eingabeRef}
            type="text"
            role="combobox"
            aria-label="Suchen"
            aria-expanded={zeilen.length > 0}
            aria-controls={zeilen.length > 0 ? listeId : undefined}
            aria-activedescendant={zeilen.length > 0 ? `${listeId}-opt-${gewaehlt}` : undefined}
            aria-autocomplete="list"
            autoComplete="off"
            spellCheck={false}
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
            placeholder="Suchen nach Kunde, Vorgang, Anlage, Rechnung, #Tag …"
            className="min-w-0 flex-1 bg-transparent text-titel-mobil text-label outline-none placeholder:text-label3"
          />
          <Taste>esc</Taste>
        </div>

        <div className="border-b-[0.5px] border-sep px-3.5 pb-3">
          <SuchFilterLeiste suche={suche} erlaubt={erlaubt} variante="office" />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pt-1.5 pb-2">
          {zeilen.length > 0 && (
            <div id={listeId} role="listbox" aria-label="Ergebnisse" className={suche.veraltet ? "opacity-60" : undefined}>
              {abschnitte.map((a) => {
                const start = offset;
                offset += a.eintraege.length;
                if (a.eintraege.length === 0) return null;
                const kopfId = `${listeId}-kopf-${a.key}`;
                return (
                  <div key={a.key}>
                    <div className="flex items-center justify-between px-2.5 pt-2.5 pb-1 text-meta font-semibold tracking-wide text-label2 uppercase">
                      <span id={kopfId}>{a.zahl ? `${a.titel} · ${a.zahl}` : a.titel}</span>
                      {a.rechts}
                    </div>
                    <div role="group" aria-labelledby={kopfId}>
                      {a.eintraege.map((e, i) => (
                        <TrefferZeile
                          key={e.key}
                          id={`${listeId}-opt-${start + i}`}
                          eintrag={e}
                          begriff={hatEingabe ? begriff : ""}
                          gewaehlt={start + i === gewaehlt}
                          onZeiger={() => setAuswahl(start + i)}
                          onOeffnen={(neuerTab) => oeffnen(e, neuerTab)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {suche.hatWeitere && <NachladenAnker onSichtbar={suche.ladeWeitere} laeuft={suche.ladeWeitereLaeuft} />}

          {wartetAufTreffer && zeilen.length === 0 && <SkeletonList count={3} className="px-2 pt-2" />}
          {hatEingabe && suche.fehler && !suche.gruppen.length && (
            <FehlerZustand fehler={suche.fehler} was="Die Suche" onErneut={suche.neuLaden} />
          )}
          {keineTreffer && <EmptyState icon={SearchX} text={`Keine Treffer für „${eingabe.trim()}“`} />}

          {!hatEingabe && tags && tags.length > 0 && (
            <div>
              <div className="px-2.5 pt-2.5 pb-1 text-meta font-semibold tracking-wide text-label2 uppercase">Tags</div>
              <div className="flex flex-wrap gap-1.5 px-2.5 pt-1 pb-1.5">
                {tags.map((tag) => (
                  <button
                    key={tag.id}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setEingabe(`#${tag.label}`);
                      eingabeRef.current?.focus();
                    }}
                    className="rounded-full bg-fill px-2.5 py-1 text-sekundaer font-medium text-label"
                  >
                    #{tag.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-4 border-t-[0.5px] border-sep px-[18px] py-[9px] text-meta text-label2">
          <span className="flex items-center gap-[5px]">
            <Taste label="Pfeil hoch">
              <ArrowUp size={11} strokeWidth={2.5} />
            </Taste>
            <Taste label="Pfeil runter">
              <ArrowDown size={11} strokeWidth={2.5} />
            </Taste>
            auswählen
          </span>
          <span className="flex items-center gap-[5px]">
            <Taste>↵</Taste> öffnen
          </span>
          <span className="flex items-center gap-[5px]">
            <Taste>{MAC ? "⌘" : "Strg"}</Taste>
            <Taste>↵</Taste> neuer Tab
          </span>
          <span className="flex items-center gap-[5px]">
            <Taste>⇥</Taste> Kategorie
          </span>
          <span className="flex-1" />
          <span className="flex items-center gap-[5px]">
            <Taste>esc</Taste> schließen
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
