import { Bell, Check, CircleDot, Phone, PhoneIncoming, PhoneOutgoing, Search, User } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { StatusPille } from "../../components/apple/StatusPille";
import { useTelefonat } from "../../components/telefonat/TelefonatProvider";
import { useAuth } from "../../context/AuthContext";
import { useTelefonatAendern, useTelefonateListe } from "../../hooks/useTelefonate";
import type { Telefonat } from "../../types";
import { istAdminRolle } from "../../utils/rollen";
import {
  TELEFONAT_ERGEBNIS_LABEL,
  TELEFONAT_RICHTUNG_LABEL,
  formatDauer,
  istRueckrufOffen,
} from "../../utils/telefonat";
import { SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";

const LIMIT = 200;

/** Filterwert für die Spalte "Rückruf": offen (alle) schließt offen (von mir) ein. */
export function rueckrufFilterWerte(t: Telefonat, meineId: string | undefined): string[] {
  if (istRueckrufOffen(t)) return t.erfasst_von === meineId ? ["offen", "offen_mir"] : ["offen"];
  return t.rueckruf_erledigt_am ? ["erledigt"] : [];
}

const zeit = (iso: string) =>
  new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** Office-Liste aller Telefonate; Standardfilter "Rückruf ist Offen, von mir". Geladen werden die letzten
 * {LIMIT} Einträge, Filter und Suche laufen im Browser (wie bei den übrigen Office-Listen). */
export function OfficeTelefonatePage() {
  const { currentUser } = useAuth();
  const telefonat = useTelefonat();
  const { data, isLoading, isError, error, refetch } = useTelefonateListe({ limit: LIMIT });
  const erledigen = useTelefonatAendern();
  const meineId = currentUser?.id;
  const istAdmin = istAdminRolle(currentUser);
  const darfBearbeiten = (t: Telefonat) => t.erfasst_von === meineId || istAdmin;

  const erfasser = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of data ?? []) map.set(t.erfasst_von, t.erfasst_von_name ?? "Unbekannt");
    return [...map].map(([wert, label]) => ({ wert, label })).sort((a, b) => a.label.localeCompare(b.label, "de"));
  }, [data]);

  const felder = useMemo<FilterFeld<Telefonat>[]>(
    () => [
      {
        key: "rueckruf",
        label: "Rückruf",
        typ: "auswahl",
        icon: Bell,
        wert: (t) => rueckrufFilterWerte(t, meineId),
        optionen: [
          { wert: "offen_mir", label: "Offen, von mir" },
          { wert: "offen", label: "Offen, von allen" },
          { wert: "erledigt", label: "Erledigt" },
        ],
      },
      {
        key: "ergebnis",
        label: "Ergebnis",
        typ: "auswahl",
        icon: CircleDot,
        wert: (t) => t.ergebnis,
        optionen: Object.entries(TELEFONAT_ERGEBNIS_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      {
        key: "richtung",
        label: "Richtung",
        typ: "auswahl",
        icon: PhoneOutgoing,
        wert: (t) => t.richtung,
        optionen: Object.entries(TELEFONAT_RICHTUNG_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      { key: "erfasser", label: "Erfasst von", typ: "person", icon: User, wert: (t) => t.erfasst_von, optionen: erfasser },
      { key: "partner", label: "Gesprächspartner", typ: "text", icon: Phone, wert: (t) => t.partner_name },
      { key: "kunde", label: "Kunde", typ: "text", icon: User, wert: (t) => t.kunde_name },
      { key: "vorgang", label: "Vorgang", typ: "text", icon: Phone, wert: (t) => t.vorgang_nummer },
      { key: "datum", label: "Datum", typ: "datum", icon: Phone, wert: (t) => t.beginn.slice(0, 10) },
    ],
    [erfasser, meineId],
  );
  const zustand = useFilterZustand({ felder });

  // Standardfilter nur beim ersten Öffnen ohne eigene Filter/Suche in der URL; wer die Pille entfernt, bekommt sie nicht zurück.
  const standardGesetzt = useRef(false);
  useEffect(() => {
    if (standardGesetzt.current) return;
    standardGesetzt.current = true;
    if (zustand.bedingungen.length === 0 && !zustand.suche) {
      zustand.hinzufuegen({ feld: "rueckruf", op: "ist", wert: ["offen_mir"] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gefiltert = sucheAnwenden(filterAnwenden(data ?? [], zustand.bedingungen, felder), zustand.sucheVerzoegert, (t) =>
    [t.partner_name, t.partner_nummer, t.kunde_name, t.vorgang_nummer, t.vorgang_titel, t.notiz, t.erfasst_von_name].join(" "),
  );

  const spalten: Spalte<Telefonat>[] = [
    { key: "datum", label: "Datum", haupt: true, render: (t) => zeit(t.beginn), sortWert: (t) => t.beginn },
    {
      key: "partner",
      label: "Gesprächspartner",
      render: (t) => (
        <span>
          {t.partner_name}
          {t.partner_nummer && <span className="text-label2"> · {t.partner_nummer}</span>}
        </span>
      ),
      sortWert: (t) => t.partner_name,
    },
    {
      key: "kunde",
      label: "Kunde",
      render: (t) =>
        t.kunde_id ? (
          <Link to={`/kunden/${t.kunde_id}`} onClick={(e) => e.stopPropagation()} className="text-tint-text hover:underline">
            {t.kunde_name ?? "Kunde"}
          </Link>
        ) : (
          "–"
        ),
      sortWert: (t) => t.kunde_name ?? "",
    },
    {
      key: "vorgang",
      label: "Vorgang",
      render: (t) =>
        t.vorgang_id ? (
          <Link to={`/vorgaenge/${t.vorgang_id}`} onClick={(e) => e.stopPropagation()} title={t.vorgang_titel ?? undefined} className="text-tint-text hover:underline">
            {t.vorgang_nummer ?? "Vorgang"}
          </Link>
        ) : (
          <span className="text-label2">ohne Vorgang</span>
        ),
      sortWert: (t) => t.vorgang_nummer ?? "",
    },
    {
      key: "richtung",
      label: "Richtung",
      render: (t) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          {t.richtung === "ausgehend" ? <PhoneOutgoing size={14} aria-hidden="true" /> : <PhoneIncoming size={14} aria-hidden="true" />}
          {TELEFONAT_RICHTUNG_LABEL[t.richtung]}
        </span>
      ),
      sortWert: (t) => t.richtung,
    },
    {
      key: "ergebnis",
      label: "Ergebnis",
      render: (t) => <StatusBadge label={TELEFONAT_ERGEBNIS_LABEL[t.ergebnis]} tone={t.ergebnis === "erreicht" ? "emerald" : "slate"} />,
      sortWert: (t) => TELEFONAT_ERGEBNIS_LABEL[t.ergebnis],
    },
    {
      key: "dauer",
      label: "Dauer",
      align: "rechts",
      render: (t) => formatDauer(t.dauer_sekunden) ?? "–",
      sortWert: (t) => t.dauer_sekunden ?? -1,
    },
    {
      key: "rueckruf",
      label: "Rückruf",
      render: (t) =>
        t.rueckruf_am ? (
          <StatusPille
            status={t.rueckruf_erledigt_am ? "erledigt" : "wartet"}
            label={t.rueckruf_erledigt_am ? "Erledigt" : zeit(t.rueckruf_am)}
          />
        ) : (
          "–"
        ),
      sortWert: (t) => (t.rueckruf_erledigt_am ? "" : (t.rueckruf_am ?? "")),
    },
    { key: "erfasser", label: "Erfasst von", render: (t) => t.erfasst_von_name ?? "–", sortWert: (t) => t.erfasst_von_name ?? "" },
  ];

  const leer = (data ?? []).length === 0;

  return (
    <div>
      <SeitenKopf titel="Telefonate" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <button type="button" onClick={() => telefonat.erfassen({ kundeWaehlbar: true })} className={NEU_BUTTON_KLASSE}>
          + Telefonat erfassen
        </button>
      </SeitenKopf>

      <FilterLeiste felder={felder} zustand={zustand} variante="office" suchPlatzhalter="Telefonate suchen…" className="mb-4" />

      {isLoading ? (
        <SkeletonList count={6} />
      ) : isError ? (
        <FehlerZustand fehler={error} was="Die Telefonate" onErneut={() => void refetch()} />
      ) : leer ? (
        <EmptyState
          icon={Phone}
          text="Noch keine Telefonate erfasst."
          action={
            <button type="button" onClick={() => telefonat.erfassen({ kundeWaehlbar: true })} className="btn-ap px-4 py-2 text-sekundaer">
              Telefonat erfassen
            </button>
          }
        />
      ) : gefiltert.length === 0 ? (
        <EmptyState
          icon={Search}
          text={zustand.sucheVerzoegert && zustand.bedingungen.length === 0 ? `Nichts gefunden für „${zustand.sucheVerzoegert}“` : "Keine Treffer für diese Filter"}
          action={
            <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
              Filter zurücksetzen
            </button>
          }
        />
      ) : (
        <SortierbareTabelle
          zeilen={gefiltert}
          spalten={spalten}
          zeilenKey={(t) => t.id}
          onWaehlen={(t) => darfBearbeiten(t) && telefonat.bearbeiten(t)}
          startSortierung={{ key: "datum", absteigend: true }}
          hervorgehoben={zustand.bedingungen.map((b) => b.feld)}
          zeilenAktionen={(t) =>
            istRueckrufOffen(t) && darfBearbeiten(t) ? (
              <button
                type="button"
                onClick={() => erledigen.mutate({ id: t.id, body: { rueckruf_erledigt: true } })}
                disabled={erledigen.isPending}
                aria-label={`Rückruf erledigt: ${t.partner_name}`}
                title="Rückruf erledigt"
                className="btn-ap flex h-8 w-8 items-center justify-center p-0 disabled:opacity-50"
              >
                <Check size={16} strokeWidth={2.5} aria-hidden="true" />
              </button>
            ) : null
          }
        />
      )}
    </div>
  );
}
