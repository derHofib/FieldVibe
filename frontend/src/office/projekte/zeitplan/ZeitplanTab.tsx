import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, ChartGantt, MessageSquareWarning, FileText, FolderCog, Info, LayoutTemplate, MoreHorizontal, Scaling, Settings2, Flag, Check, X } from "lucide-react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../../api/client";
import { usersApi, zeitplanApi } from "../../../api/endpoints";
import { EmptyState } from "../../../components/EmptyState";
import { SearchableSelect } from "../../../components/SearchableSelect";
import { PulldownMenu, type PulldownItem } from "../../../components/apple/PulldownMenu";
import { SegmentedControl } from "../../../components/apple/SegmentedControl";
import { Sheet } from "../../../components/apple/Sheet";
import { openPdfBlob } from "../../../utils/pdf";
import type { Zeitplan, ZeitplanAbhaengigkeit, ZeitplanAbhaengigkeitArt, ZeitplanElement, ZeitplanElementUpdate, ZeitplanTyp, ZeitplanVerschiebeModus } from "../../../types";
import { AntraegeSheet } from "./AntraegeSheet";
import { offeneAntraegeGesamt } from "./antragLogik";
import { ElementDetailSheet } from "./ElementDetailSheet";
import { GanttLegende } from "./GanttLegende";
import { GanttListe } from "./GanttListe";
import { GanttZeitleiste, type GanttZiehAnzeige } from "./GanttZeitleiste";
import { BasisplanSpeichernSheet, BasisplaeneVerwaltenSheet, StraffenSheet, VorlageEinfuegenSheet, VorlageSpeichernSheet } from "./ZeitplanDialoge";
import { VerbindungsPopover } from "./VerbindungsPopover";
import {
  ART_ERKLAERUNG,
  ART_LABEL,
  PX_PRO_TAG,
  SCHRITT_STANDARD_DAUER,
  ZEILEN_HOEHE,
  anzeigeZeitraeume,
  balkenRechteck,
  baueZeilen,
  berechneVorschau,
  elementAenderung,
  formatBereich,
  formatKurz,
  formatTag,
  heuteTag,
  istGueltigesVerbindungsziel,
  formatAbweichung,
  kritischInfo,
  parseTag,
  phaseVerschieben,
  pixelZuTagen,
  standardStart,
  tagZuX,
  verbindungsArtBeimZiehen,
  zeitbereich,
  type Aenderung,
  type Entwurf,
  type Zoom,
  type ZiehArt,
} from "./zeitplanLogik";

const ZOOM_OPTIONEN: { wert: Zoom; label: string }[] = [
  { wert: "tag", label: "Tag" },
  { wert: "woche", label: "Woche" },
  { wert: "monat", label: "Monat" },
];
const MODUS_OPTIONEN: { wert: ZeitplanVerschiebeModus; label: string }[] = [
  { wert: "bei_konflikt", label: "Bei Konflikt" },
  { wert: "immer", label: "Immer mitschieben" },
];
const MODUS_ERKLAERUNG =
  "Bei Konflikt: Nachfolger werden nur nach hinten geschoben, wenn sie sonst vor dem Ende ihres Vorgängers lägen. " +
  "Immer mitschieben: Nachfolger wandern immer um dieselbe Zeit wie das Ende ihres Vorgängers mit – auch nach vorne.";

interface ZiehZustand {
  art: ZiehArt | "verbinden";
  id: string;
  delta: number;
  vorschau: Map<string, Aenderung>;
  zeigerX?: number;
  zeigerY?: number;
  zielId?: string | null;
  quelleSeite?: "anfang" | "ende";
  /** Art, die beim Loslassen am aktuellen Ziel entstuende (null: kein gueltiges Ziel). */
  verbindungsArt?: ZeitplanAbhaengigkeitArt | null;
  /** Zeiger steht ueber einer Zeile, aber dort ist keine Verbindung moeglich. */
  ungueltig?: boolean;
}

function hinweisText(z: ZiehZustand): string {
  if (z.verbindungsArt && z.zielId) return `${ART_LABEL[z.verbindungsArt]}: ${ART_ERKLAERUNG[z.verbindungsArt]}`;
  if (z.ungueltig) return z.quelleSeite === "anfang" ? "Von einem Anfang aus nur auf die linke Hälfte des Ziels (Anfang → Anfang)" : "Hier ist keine Verbindung möglich";
  return z.quelleSeite === "anfang"
    ? "Auf den Anfang eines Schritts ziehen: Anfang → Anfang"
    : "Auf ein Ziel ziehen: linke Hälfte Ende → Anfang, rechte Hälfte Ende → Ende";
}

function fehlerText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Die Änderung konnte nicht gespeichert werden.";
}

function vorschauAnwenden(zp: Zeitplan, vorschau: Map<string, Aenderung>): Zeitplan {
  if (vorschau.size === 0) return zp;
  return {
    ...zp,
    elemente: zp.elemente.map((e) => {
      const v = vorschau.get(e.id);
      return v ? { ...e, start_am: v.start_am, ende_am: e.typ === "meilenstein" ? v.start_am : v.ende_am } : e;
    }),
  };
}

const kritischSchluessel = (projektId: string) => `zeitplan.kritischerPfad.${projektId}`;

function kritischLesen(projektId: string): boolean {
  try {
    return window.localStorage.getItem(kritischSchluessel(projektId)) === "1";
  } catch {
    return false;
  }
}

type DialogArt = "antraege" | "basisplan-speichern" | "basisplaene" | "straffen" | "vorlage-einfuegen" | "vorlage-speichern";

function useSchmalerViewport(): boolean {
  const abfrage = "(max-width: 767px)";
  const [schmal, setSchmal] = useState(() => typeof window !== "undefined" && window.matchMedia(abfrage).matches);
  useEffect(() => {
    const mql = window.matchMedia(abfrage);
    const aufAenderung = () => setSchmal(mql.matches);
    mql.addEventListener("change", aufAenderung);
    return () => mql.removeEventListener("change", aufAenderung);
  }, []);
  return schmal;
}

/** Tab "Zeitplan" der Projekt-Detailansicht (Office, Desktop): Gantt-Diagramm
 * mit Phasen, Schritten, Meilensteinen und Abhaengigkeiten. Daten und
 * Mutationen laufen ueber React Query (Key ["projekt-zeitplan", id]); jede
 * mutierende Antwort ist der komplette Zeitplan und ersetzt den Cache. Das
 * Backend bleibt fuer die Verschiebe-Regeln massgeblich, die Vorschau beim
 * Ziehen (zeitplanLogik.ts) spiegelt sie nur fuer sofortiges Feedback. */
export function ZeitplanTab({ projektId }: { projektId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [basisplanId, setBasisplanId] = useState<string | null>(null);
  // Der Basisplan gehoert zum Query-Key, damit der Vergleich nicht mit dem normalen Stand kollidiert.
  const queryKey = useMemo(() => ["projekt-zeitplan", projektId, basisplanId], [projektId, basisplanId]);
  const schmal = useSchmalerViewport();

  // keepPreviousData: beim Wechsel des Vergleichs bleibt der Plan stehen (kein Flackern, Scrollposition bleibt).
  const {
    data: zeitplan,
    isLoading,
    error,
  } = useQuery({ queryKey, queryFn: () => zeitplanApi.get(projektId, basisplanId), placeholderData: keepPreviousData });
  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl });
  const { data: basisplaene } = useQuery({ queryKey: ["projekt-basisplaene", projektId], queryFn: () => zeitplanApi.basisplaene(projektId) });

  const [zoom, setZoom] = useState<Zoom>("tag");
  const [fehler, setFehler] = useState<string | null>(null);
  const [eingeklappt, setEingeklappt] = useState<Set<string>>(new Set());
  const [bearbeiteId, setBearbeiteId] = useState<string | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [dialog, setDialog] = useState<{ art: "fortschritt" | "zuweisen"; element: ZeitplanElement } | null>(null);
  const [depPopover, setDepPopover] = useState<{ depId: string; x: number; y: number } | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [zieh, setZieh] = useState<ZiehZustand | null>(null);
  // Kritisch/Puffer/Basisplan-Werte kommen nur vom Server und werden NICHT lokal neu berechnet: beim Ziehen
  // bleibt die Hervorhebung auf dem Stand vor dem Ziehen stehen (Vorschau verschiebt nur die Balken) und
  // aktualisiert sich mit der Server-Antwort nach dem Loslassen.
  const [kritischModus, setKritischModus] = useState(() => kritischLesen(projektId));
  const [offenerDialog, setOffenerDialog] = useState<DialogArt | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const ziehRef = useRef<{ delta: number } | null>(null);
  const hatInitialGescrollt = useRef(false);
  const linksTagRef = useRef<number | null>(null);

  const heute = heuteTag();
  const elemente = useMemo(() => zeitplan?.elemente ?? [], [zeitplan]);
  const abhaengigkeiten = useMemo(() => zeitplan?.abhaengigkeiten ?? [], [zeitplan]);
  const modus = zeitplan?.verschiebe_modus ?? "bei_konflikt";
  // Mindestens ~1200 px Breite je Zoom, sonst wirkt der Monatszoom bei kurzen Plaenen abgeschnitten.
  const bereich = useMemo(() => zeitbereich(elemente, heute, Math.max(63, Math.ceil(1200 / PX_PRO_TAG[zoom]))), [elemente, heute, zoom]);
  const zeilen = useMemo(() => baueZeilen(elemente, eingeklappt, entwurf), [elemente, eingeklappt, entwurf]);
  const positionen = useMemo(() => anzeigeZeitraeume(elemente, zieh?.vorschau), [elemente, zieh?.vorschau]);

  // Aktueller Stand fuer die window-Listener waehrend des Ziehens (die
  // Closures wuerden sonst den Stand vom Ziehbeginn festhalten).
  const aktuell = useRef({ elemente, abhaengigkeiten, modus, zoom, zeilen, bereich, positionen });
  aktuell.current = { elemente, abhaengigkeiten, modus, zoom, zeilen, bereich, positionen };

  // --- Mutationen ---------------------------------------------------------

  // Mutations-Antworten kommen ohne Basisplan-Daten (kein basisplan_id im Aufruf). Bei aktivem
  // Vergleich daher: Basiswerte aus dem Cache uebernehmen (kein Flackern) und neu laden.
  const ersetzen = useCallback(
    (zp: Zeitplan) => {
      if (!basisplanId) {
        queryClient.setQueryData(queryKey, zp);
        return;
      }
      const alt = queryClient.getQueryData<Zeitplan>(queryKey);
      const altNachId = new Map((alt?.elemente ?? []).map((e) => [e.id, e]));
      queryClient.setQueryData(queryKey, {
        ...zp,
        elemente: zp.elemente.map((e) => {
          const a = altNachId.get(e.id);
          return a ? { ...e, basis_start_am: a.basis_start_am, basis_ende_am: a.basis_ende_am, abweichung_tage: a.abweichung_tage } : e;
        }),
      });
      queryClient.invalidateQueries({ queryKey });
    },
    [queryClient, queryKey, basisplanId],
  );

  const pdfExport = useMutation({
    mutationFn: () => zeitplanApi.pdf(projektId, basisplanId, kritischModus),
    onSuccess: openPdfBlob,
    onError: (e) => setFehler(fehlerText(e)),
  });

  const aendern = useMutation({
    mutationFn: (aufruf: () => Promise<Zeitplan>) => aufruf(),
    onSuccess: ersetzen,
    onError: (e) => setFehler(fehlerText(e)),
  });

  const verschieben = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ZeitplanElementUpdate; vorschau: Map<string, Aenderung> }) =>
      zeitplanApi.updateElement(projektId, id, body),
    onMutate: async ({ vorschau }) => {
      await queryClient.cancelQueries({ queryKey });
      const vorher = queryClient.getQueryData<Zeitplan>(queryKey);
      if (vorher) queryClient.setQueryData(queryKey, vorschauAnwenden(vorher, vorschau));
      return { vorher };
    },
    onSuccess: ersetzen,
    onError: (e, _v, ctx) => {
      if (ctx?.vorher) queryClient.setQueryData(queryKey, ctx.vorher);
      setFehler(fehlerText(e));
    },
  });

  function patch(id: string, body: ZeitplanElementUpdate) {
    setFehler(null);
    aendern.mutate(() => zeitplanApi.updateElement(projektId, id, body));
  }

  // --- Ziehen / Tastatur ------------------------------------------------------

  function ziehVorschau(id: string, art: ZiehArt, delta: number): Map<string, Aenderung> {
    const { elemente: el, abhaengigkeiten: deps, modus: m } = aktuell.current;
    const element = el.find((e) => e.id === id);
    if (!element) return new Map();
    let direkt: Map<string, Aenderung>;
    if (element.typ === "phase") direkt = art === "verschieben" ? phaseVerschieben(el, id, delta) : new Map();
    else {
      const a = elementAenderung(element, art, delta);
      direkt = a ? new Map([[id, a]]) : new Map();
    }
    return direkt.size ? berechneVorschau(el, deps, m, direkt) : new Map();
  }

  function verschiebungSpeichern(id: string, art: ZiehArt, delta: number) {
    const vorschau = ziehVorschau(id, art, delta);
    if (vorschau.size === 0) return;
    const element = aktuell.current.elemente.find((e) => e.id === id);
    let body: ZeitplanElementUpdate;
    if (element?.typ === "phase") {
      const spanne = anzeigeZeitraeume(aktuell.current.elemente).get(id);
      if (!spanne) return;
      body = { start_am: formatTag(spanne.start + delta), ende_am: formatTag(spanne.ende + delta) };
    } else {
      const v = vorschau.get(id)!;
      body = { start_am: v.start_am, ende_am: v.ende_am };
    }
    setFehler(null);
    verschieben.mutate({ id, body, vorschau });
  }

  function ziehStart(e: ReactPointerEvent, id: string, art: ZiehArt) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    // Datum kommt aus der Bestellung -- nicht ziehbar (der Server lehnt es ohnehin mit 400 ab).
    if (aktuell.current.elemente.find((el) => el.id === id)?.datum_gesperrt) return;
    const startX = e.clientX;
    ziehRef.current = { delta: 0 };
    setZieh({ art, id, delta: 0, vorschau: new Map() });
    document.body.style.userSelect = "none";

    const aufBewegen = (ev: PointerEvent) => {
      const delta = pixelZuTagen(ev.clientX - startX, aktuell.current.zoom);
      if (ziehRef.current && delta !== ziehRef.current.delta) {
        ziehRef.current.delta = delta;
        setZieh({ art, id, delta, vorschau: ziehVorschau(id, art, delta) });
      }
    };
    const aufraeumen = () => {
      window.removeEventListener("pointermove", aufBewegen);
      window.removeEventListener("pointerup", aufLoslassen);
      window.removeEventListener("pointercancel", aufAbbrechen);
      window.removeEventListener("keydown", aufEsc, true);
      document.body.style.userSelect = "";
      ziehRef.current = null;
      setZieh(null);
    };
    const aufLoslassen = () => {
      const delta = ziehRef.current?.delta ?? 0;
      aufraeumen();
      if (delta !== 0) verschiebungSpeichern(id, art, delta);
    };
    const aufAbbrechen = () => aufraeumen();
    const aufEsc = (ev: KeyboardEvent) => {
      if (ev.key !== "Escape") return;
      ev.stopPropagation(); // sonst schliesst Esc auch das Seitenpanel
      aufraeumen();
    };
    window.addEventListener("pointermove", aufBewegen);
    window.addEventListener("pointerup", aufLoslassen);
    window.addEventListener("pointercancel", aufAbbrechen);
    window.addEventListener("keydown", aufEsc, true);
  }

  function verbindenStart(e: ReactPointerEvent, id: string, seite: "anfang" | "ende") {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    document.body.style.userSelect = "none";
    let zielId: string | null = null;
    let art: ZeitplanAbhaengigkeitArt | null = null;

    const aufBewegen = (ev: PointerEvent) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      const { zeilen: z, elemente: el, abhaengigkeiten: deps, positionen: pos, zoom: zm, bereich: br } = aktuell.current;
      const index = Math.floor(y / ZEILEN_HOEHE);
      const zeile = z[index];
      zielId = null;
      art = null;
      let ungueltig = false;
      if (zeile?.art === "element") {
        const zeitraum = pos.get(zeile.element.id);
        if (istGueltigesVerbindungsziel(el, deps, id, zeile.element.id) && zeitraum) {
          const a = verbindungsArtBeimZiehen(seite, balkenRechteck(zeile.element.typ, zeitraum, index, zm, br.ursprung), x);
          if (a) {
            zielId = zeile.element.id;
            art = a;
          } else ungueltig = true;
        } else if (zeile.element.id !== id) ungueltig = true;
      }
      setZieh({ art: "verbinden", id, delta: 0, vorschau: new Map(), zeigerX: x, zeigerY: y, zielId, quelleSeite: seite, verbindungsArt: art, ungueltig });
    };
    const aufraeumen = () => {
      window.removeEventListener("pointermove", aufBewegen);
      window.removeEventListener("pointerup", aufLoslassen);
      window.removeEventListener("pointercancel", aufAbbrechen);
      window.removeEventListener("keydown", aufEsc, true);
      document.body.style.userSelect = "";
      setZieh(null);
    };
    const aufLoslassen = () => {
      const ziel = zielId;
      const gewaehlteArt = art;
      aufraeumen();
      if (ziel && gewaehlteArt) {
        setFehler(null);
        aendern.mutate(() => zeitplanApi.createAbhaengigkeit(projektId, { vorgaenger_id: id, nachfolger_id: ziel, art: gewaehlteArt }));
      }
    };
    const aufAbbrechen = () => aufraeumen();
    const aufEsc = (ev: KeyboardEvent) => {
      if (ev.key !== "Escape") return;
      ev.stopPropagation();
      aufraeumen();
    };
    window.addEventListener("pointermove", aufBewegen);
    window.addEventListener("pointerup", aufLoslassen);
    window.addEventListener("pointercancel", aufAbbrechen);
    window.addEventListener("keydown", aufEsc, true);
    setZieh({ art: "verbinden", id, delta: 0, vorschau: new Map(), zielId: null, quelleSeite: seite });
  }

  function aufTaste(e: ReactKeyboardEvent, id: string) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    if (aktuell.current.elemente.find((el) => el.id === id)?.datum_gesperrt) return;
    const richtung = e.key === "ArrowRight" ? 1 : -1;
    if (e.shiftKey && e.altKey) verschiebungSpeichern(id, "dauer", richtung);
    else verschiebungSpeichern(id, "verschieben", richtung * (e.shiftKey ? 7 : 1));
  }

  // --- Anlegen / Bearbeiten / Loeschen -------------------------------------------------

  function entwurfFertig(typ: ZeitplanTyp, phaseId: string | null, titel: string | null) {
    setEntwurf(null);
    if (!titel) return;
    setFehler(null);
    if (typ === "phase") {
      aendern.mutate(() => zeitplanApi.createElement(projektId, { typ, titel }));
      return;
    }
    const start = standardStart(elemente, phaseId, heute);
    const ende = typ === "schritt" ? start + SCHRITT_STANDARD_DAUER - 1 : start;
    aendern.mutate(() =>
      zeitplanApi.createElement(projektId, { typ, titel, phase_id: phaseId, start_am: formatTag(start), ende_am: formatTag(ende) }),
    );
  }

  function loeschen(e: ZeitplanElement) {
    const text = e.typ === "phase" ? `Phase „${e.titel}“ wirklich löschen?` : `„${e.titel}“ wirklich löschen?`;
    if (!window.confirm(text)) return;
    setFehler(null);
    aendern.mutate(() => zeitplanApi.removeElement(projektId, e.id));
  }

  function depKlick(dep: ZeitplanAbhaengigkeit, position: { x: number; y: number }) {
    setDepPopover({ depId: dep.id, ...position });
  }

  // --- Scroll: beim ersten Laden auf "heute"/ersten Termin, bei Zoom-Wechsel auf dasselbe Datum

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !zeitplan || hatInitialGescrollt.current) return;
    hatInitialGescrollt.current = true;
    const starts = elemente.filter((e) => e.start_am).map((e) => parseTag(e.start_am!));
    const ziel = starts.length ? Math.min(heute, ...starts) : heute;
    el.scrollLeft = Math.max(0, tagZuX(ziel - 2, bereich.ursprung, zoom));
  }, [zeitplan, elemente, heute, bereich.ursprung, zoom]);

  const zoomWechsel = useCallback(
    (neu: Zoom) => {
      const el = scrollRef.current;
      if (el) linksTagRef.current = bereich.ursprung + el.scrollLeft / PX_PRO_TAG[zoom];
      setZoom(neu);
    },
    [bereich.ursprung, zoom],
  );
  useEffect(() => {
    const el = scrollRef.current;
    if (el && linksTagRef.current !== null) {
      el.scrollLeft = tagZuX(linksTagRef.current, bereich.ursprung, zoom);
      linksTagRef.current = null;
    }
  }, [zoom, bereich.ursprung]);

  function kritischUmschalten(neu: boolean) {
    setKritischModus(neu);
    try {
      window.localStorage.setItem(kritischSchluessel(projektId), neu ? "1" : "0");
    } catch {
      /* Speicher nicht verfuegbar (privates Fenster): Zustand gilt nur fuer diese Sitzung. */
    }
  }

  // --- Darstellung ------------------------------------------------------------------

  if (isLoading) return <p className="p-4 text-sm text-label2">Zeitplan wird geladen …</p>;
  if (error || !zeitplan) {
    return (
      <p role="alert" className="p-4 text-sm text-st-fehlt">
        Zeitplan konnte nicht geladen werden.
      </p>
    );
  }

  if (schmal) return <ZeitplanSchmal elemente={elemente} />;

  const leer = elemente.length === 0 && !entwurf;
  const offeneGesamt = offeneAntraegeGesamt(elemente);
  const ziehAnzeige: GanttZiehAnzeige | null = zieh
    ? {
        id: zieh.id,
        art: zieh.art,
        info: (() => {
          if (zieh.art === "verbinden") return null;
          const z = positionen.get(zieh.id);
          const typ = elemente.find((e) => e.id === zieh.id)?.typ;
          if (!z) return null;
          return typ === "meilenstein" ? formatKurz(z.start) : formatBereich(formatTag(z.start), formatTag(z.ende));
        })(),
        zeigerX: zieh.zeigerX,
        zeigerY: zieh.zeigerY,
        zielId: zieh.zielId,
        quelleSeite: zieh.quelleSeite,
        verbindungsArt: zieh.verbindungsArt,
      }
    : null;
  const depOffen = depPopover ? abhaengigkeiten.find((d) => d.id === depPopover.depId) ?? null : null;
  const detailElement = detailId ? elemente.find((e) => e.id === detailId) ?? null : null;
  const detailZeitraum = detailElement ? positionen.get(detailElement.id) : undefined;

  const depTitel = (id: string) => elemente.find((e) => e.id === id)?.titel ?? "";

  const aktiverBasisplan = basisplanId ? basisplaene?.find((b) => b.id === basisplanId) ?? null : null;
  const vergleichAktiv = !!basisplanId && !!aktiverBasisplan;
  const vergleichItems: PulldownItem[] = [
    { label: `${basisplanId ? "" : "✓ "}Kein Vergleich`, onSelect: () => setBasisplanId(null) },
    ...((basisplaene ?? []).length ? (["trenner"] as const) : []),
    ...(basisplaene ?? []).map((b) => ({ label: `${b.id === basisplanId ? "✓ " : ""}${b.name}`, onSelect: () => setBasisplanId(b.id) })),
  ];
  const weitereItems: PulldownItem[] = [
    ...(leer ? [] : [{ label: "Basisplan speichern …", icon: BookmarkPlus, onSelect: () => setOffenerDialog("basisplan-speichern") }]),
    { label: "Basispläne verwalten …", icon: Settings2, onSelect: () => setOffenerDialog("basisplaene") },
    "trenner",
    { label: "Aus Vorlage einfügen …", icon: LayoutTemplate, onSelect: () => setOffenerDialog("vorlage-einfuegen") },
    ...(leer ? [] : [{ label: "Als Vorlage speichern …", icon: LayoutTemplate, onSelect: () => setOffenerDialog("vorlage-speichern") }]),
    { label: "Vorlagen verwalten …", icon: FolderCog, onSelect: () => navigate("/projekte/vorlagen") },
    ...(leer ? [] : (["trenner", { label: "PDF exportieren", icon: FileText, onSelect: () => pdfExport.mutate() }] as PulldownItem[])),
  ];
  const planInfo = [
    ...(kritischModus && detailElement ? [kritischInfo(detailElement)] : []),
    ...(vergleichAktiv && detailElement?.basis_start_am && detailElement.basis_ende_am
      ? [
          `Basisplan „${aktiverBasisplan!.name}“: ${
            detailElement.typ === "meilenstein" ? formatKurz(parseTag(detailElement.basis_start_am)) : formatBereich(detailElement.basis_start_am, detailElement.basis_ende_am)
          }${formatAbweichung(detailElement.abweichung_tage) ? ` (${formatAbweichung(detailElement.abweichung_tage)!.text})` : ""}`,
        ]
      : []),
  ].filter((t): t is string => !!t);

  return (
    <div id="projekt-tabpanel-zeitplan" role="tabpanel" aria-labelledby="projekt-tab-zeitplan" className="space-y-3 p-4 pt-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <SegmentedControl ariaLabel="Zoomstufe" optionen={ZOOM_OPTIONEN} wert={zoom} onChange={zoomWechsel} />
        <div className="flex items-center gap-2" title={MODUS_ERKLAERUNG}>
          <span className="text-xs text-label2">Verschieben:</span>
          <SegmentedControl
            ariaLabel="Verschiebe-Modus"
            optionen={MODUS_OPTIONEN}
            wert={modus}
            onChange={(m) => {
              if (m === modus) return;
              setFehler(null);
              aendern.mutate(() => zeitplanApi.updateEinstellungen(projektId, { verschiebe_modus: m }));
            }}
          />
          <Info size={15} strokeWidth={2} className="text-label2" aria-label={MODUS_ERKLAERUNG} role="img" />
        </div>
        {/* Immer im Fluss vorhanden (leer = unsichtbar), damit die Zeile beim Ziehen nicht springt. */}
        <p aria-live="polite" className="min-h-5 min-w-0 flex-1 text-right text-xs text-label2">
          {zieh?.art === "verbinden" ? hinweisText(zieh) : ""}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Zeitplan-Werkzeuge">
        <button
          type="button"
          role="switch"
          aria-checked={kritischModus}
          onClick={() => kritischUmschalten(!kritischModus)}
          className={`btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm ${kritischModus ? "text-st-fehlt" : ""}`}
          style={kritischModus ? { borderColor: "var(--st-fehlt-dot)" } : undefined}
          title="Hebt Schritte hervor, deren Verzögerung das Projektende verschiebt"
        >
          <Flag size={14} strokeWidth={2} aria-hidden="true" />
          Kritischer Pfad
          {kritischModus && <Check size={14} strokeWidth={2.5} aria-hidden="true" />}
        </button>

        <PulldownMenu
          ariaLabel="Vergleich mit Basisplan"
          items={vergleichItems}
          trigger={({ offen, toggeln, triggerRef }) => (
            <button
              ref={triggerRef}
              type="button"
              onClick={toggeln}
              aria-haspopup="menu"
              aria-expanded={offen}
              className="btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm"
            >
              <Scaling size={14} strokeWidth={2} aria-hidden="true" />
              <span>Vergleich:</span>
              <span className="max-w-[160px] truncate font-semibold">{aktiverBasisplan?.name ?? "—"}</span>
            </button>
          )}
        />

        <button
          type="button"
          onClick={() => setOffenerDialog("antraege")}
          className={`btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm ${offeneGesamt > 0 ? "text-st-arbeit" : ""}`}
          style={offeneGesamt > 0 ? { borderColor: "var(--st-arbeit-dot)" } : undefined}
          title="Änderungsanträge der Techniker"
        >
          <MessageSquareWarning size={14} strokeWidth={2} aria-hidden="true" />
          Anträge ({offeneGesamt})
        </button>

        <button
          type="button"
          onClick={() => setOffenerDialog("straffen")}
          disabled={leer}
          className="btn-ap px-3 py-1.5 text-sm disabled:opacity-50"
          title="Schritte auf den frühesten möglichen Termin ziehen"
        >
          Plan straffen
        </button>

        <PulldownMenu
          ariaLabel="Weitere Zeitplan-Aktionen"
          items={weitereItems}
          trigger={({ offen, toggeln, triggerRef }) => (
            <button
              ref={triggerRef}
              type="button"
              onClick={toggeln}
              aria-haspopup="menu"
              aria-expanded={offen}
              aria-label="Weitere Aktionen"
              className="btn-ap-toolbar"
            >
              <MoreHorizontal size={16} strokeWidth={2} aria-hidden="true" />
            </button>
          )}
        />
        {pdfExport.isPending && <span className="text-xs text-label2">PDF wird erstellt …</span>}
      </div>

      {fehler && (
        <div role="alert" className="flex items-start gap-2 rounded-[10px] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          <span className="flex-1">{fehler}</span>
          <button type="button" onClick={() => setFehler(null)} aria-label="Meldung schließen" className="shrink-0">
            <X size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      )}

      {leer ? (
        <EmptyState
          icon={ChartGantt}
          text="Noch kein Zeitplan — lege die erste Phase an"
          action={
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setEntwurf({ typ: "phase", phaseId: null })} className="btn-ap btn-ap-primary px-3 py-1.5 text-sm">
                + Phase
              </button>
              <button type="button" onClick={() => setOffenerDialog("vorlage-einfuegen")} className="btn-ap px-3 py-1.5 text-sm">
                Aus Vorlage starten
              </button>
            </div>
          }
        />
      ) : (
        <div ref={scrollRef} className="max-h-[calc(100vh-190px)] overflow-auto rounded-[12px] bg-card">
          <div className="flex" style={{ width: "max-content", minWidth: "100%" }}>
            <GanttListe
              zeilen={zeilen}
              eingeklappt={eingeklappt}
              bearbeiteId={bearbeiteId}
              kritischModus={kritischModus}
              vergleich={vergleichAktiv}
              onToggle={(id) =>
                setEingeklappt((s) => {
                  const n = new Set(s);
                  if (!n.delete(id)) n.add(id);
                  return n;
                })
              }
              onBearbeiteStart={setBearbeiteId}
              onBearbeiteEnde={() => setBearbeiteId(null)}
              onUmbenennen={(id, titel) => patch(id, { titel })}
              onEntwurfStart={(typ, phaseId) => setEntwurf({ typ, phaseId })}
              onEntwurfFertig={entwurfFertig}
              onFortschritt={(element) => setDialog({ art: "fortschritt", element })}
              onZuweisen={(element) => setDialog({ art: "zuweisen", element })}
              onDetails={(element) => setDetailId(element.id)}
              onLoeschen={loeschen}
            />
            <GanttZeitleiste
              zeilen={zeilen}
              positionen={positionen}
              abhaengigkeiten={abhaengigkeiten}
              zoom={zoom}
              bereich={bereich}
              heute={heute}
              zieh={ziehAnzeige}
              ausgewaehltDepId={depPopover?.depId ?? null}
              kritischModus={kritischModus}
              vergleich={vergleichAktiv}
              svgRef={svgRef}
              onZiehStart={ziehStart}
              onVerbindenStart={verbindenStart}
              onTaste={aufTaste}
              onDepKlick={depKlick}
            />
          </div>
        </div>
      )}

      {!leer && <GanttLegende />}

      {depPopover && depOffen && (
        <VerbindungsPopover
          abhaengigkeit={depOffen}
          position={{ x: depPopover.x, y: depPopover.y }}
          vorgaengerTitel={depTitel(depOffen.vorgaenger_id)}
          nachfolgerTitel={depTitel(depOffen.nachfolger_id)}
          onClose={() => setDepPopover(null)}
          onVersatz={(tage) => {
            setFehler(null);
            aendern.mutate(() => zeitplanApi.updateAbhaengigkeit(projektId, depOffen.id, { versatz_tage: tage }));
          }}
          onArt={(art) => {
            setFehler(null);
            aendern.mutate(() => zeitplanApi.updateAbhaengigkeit(projektId, depOffen.id, { art }));
          }}
          onLoeschen={() => {
            setFehler(null);
            aendern.mutate(() => zeitplanApi.removeAbhaengigkeit(projektId, depOffen.id));
            setDepPopover(null);
          }}
        />
      )}

      {detailElement && (
        <ElementDetailSheet
          projektId={projektId}
          element={detailElement}
          zeitraumText={
            detailZeitraum
              ? detailElement.typ === "meilenstein"
                ? formatKurz(detailZeitraum.start)
                : formatBereich(formatTag(detailZeitraum.start), formatTag(detailZeitraum.ende))
              : "Ohne Datum"
          }
          planInfo={planInfo}
          fehler={fehler}
          busy={aendern.isPending}
          onPatch={(body) => patch(detailElement.id, body)}
          onClose={() => {
            setDetailId(null);
            setFehler(null);
          }}
        />
      )}

      {offenerDialog === "antraege" && <AntraegeSheet projektId={projektId} onClose={() => setOffenerDialog(null)} onZeitplan={ersetzen} />}
      {offenerDialog === "basisplan-speichern" && <BasisplanSpeichernSheet projektId={projektId} onClose={() => setOffenerDialog(null)} />}
      {offenerDialog === "basisplaene" && (
        <BasisplaeneVerwaltenSheet
          projektId={projektId}
          onClose={() => setOffenerDialog(null)}
          onGeloescht={(id) => setBasisplanId((aktuellId) => (aktuellId === id ? null : aktuellId))}
        />
      )}
      {offenerDialog === "straffen" && (
        <StraffenSheet
          projektId={projektId}
          phasen={elemente.filter((e) => e.typ === "phase")}
          onClose={() => setOffenerDialog(null)}
          onUebernommen={ersetzen}
        />
      )}
      {offenerDialog === "vorlage-einfuegen" && (
        <VorlageEinfuegenSheet projektId={projektId} elemente={elemente} onClose={() => setOffenerDialog(null)} onAngewendet={ersetzen} />
      )}
      {offenerDialog === "vorlage-speichern" && <VorlageSpeichernSheet projektId={projektId} onClose={() => setOffenerDialog(null)} />}

      {dialog && (
        <ZeilenDialog
          key={`${dialog.art}-${dialog.element.id}`}
          art={dialog.art}
          element={dialog.element}
          users={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
          onClose={() => setDialog(null)}
          onSpeichern={(body) => {
            patch(dialog.element.id, body);
            setDialog(null);
          }}
        />
      )}
    </div>
  );
}

function ZeilenDialog({
  art,
  element,
  users,
  onClose,
  onSpeichern,
}: {
  art: "fortschritt" | "zuweisen";
  element: ZeitplanElement;
  users: { value: string; label: string }[];
  onClose: () => void;
  onSpeichern: (body: ZeitplanElementUpdate) => void;
}) {
  const [fortschritt, setFortschritt] = useState(element.fortschritt);
  const [nutzer, setNutzer] = useState(element.zugewiesen_an ?? "");
  const speichern = () =>
    onSpeichern(art === "fortschritt" ? { fortschritt } : { zugewiesen_an: nutzer || null });

  return (
    <Sheet
      offen
      onClose={onClose}
      titel={art === "fortschritt" ? "Fortschritt setzen" : "Zuweisen"}
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button type="button" onClick={speichern} className="text-[17px] font-semibold text-tint-text">
          Sichern
        </button>
      }
    >
      <div className="space-y-3 p-4">
        <p className="truncate text-sm text-label2">{element.titel}</p>
        {art === "fortschritt" ? (
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={fortschritt}
              onChange={(e) => setFortschritt(Number(e.target.value))}
              aria-label="Fortschritt in Prozent"
              className="flex-1"
            />
            <span className="w-12 text-right text-[17px] text-label tabular-nums">{fortschritt} %</span>
          </div>
        ) : (
          <SearchableSelect value={nutzer} onChange={setNutzer} placeholder="Nicht zugewiesen" options={users} />
        )}
      </div>
    </Sheet>
  );
}

/** Schmale Viewports (< 768 px): kein Gantt, nur Hinweis und read-only-Liste. */
function ZeitplanSchmal({ elemente }: { elemente: ZeitplanElement[] }) {
  const zeilen = baueZeilen(elemente, new Set(), null).filter((z) => z.art === "element");
  const pos = anzeigeZeitraeume(elemente);
  return (
    <div id="projekt-tabpanel-zeitplan" role="tabpanel" aria-labelledby="projekt-tab-zeitplan" className="space-y-3 p-4 pt-0">
      <p className="text-sm text-label2">Zeitplan ist für größere Bildschirme ausgelegt</p>
      <ul className="space-y-1.5">
        {zeilen.map((z) => {
          if (z.art !== "element") return null;
          const e = z.element;
          const p = pos.get(e.id);
          return (
            <li key={e.id} className="card-ap px-3 py-2" style={{ marginLeft: z.ebene * 16 }}>
              <p className={`text-[15px] text-label ${e.typ === "phase" ? "font-semibold" : ""}`}>{e.titel}</p>
              <p className="text-xs text-label2">
                {p ? (e.typ === "meilenstein" ? formatKurz(p.start) : formatBereich(formatTag(p.start), formatTag(p.ende))) : "Ohne Datum"}
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

