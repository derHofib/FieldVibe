import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Sparkles, Undo2, User as UserIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { usersApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { StatusPille } from "../../components/apple/StatusPille";
import { STATUS_PILLE_KLASSE } from "../../components/apple/status";
import { ClaudeMarke } from "../../components/formModul/ClaudeMarke";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { zuServerParametern } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { SkeletonList } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { useAuth } from "../../context/AuthContext";
import { useKiAktion, useKiAktionenListe, useKiRueckgaengig } from "../../hooks/useKiAktionen";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import type { KiAktion, KiAktionenFilter, KiAktionStatus } from "../../types/ki";
import { datumServerParameter } from "../../utils/datumFilterParameter";
import { ListeMitPanel } from "../ListeMitPanel";
import { Karte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import { seitenText } from "../protokoll/protokollUtils";
import {
  datumUhrzeit,
  gruppiereAenderungen,
  KI_STATUS_LABEL,
  KI_STATUS_TON,
  KI_STUFE_LABEL,
  KI_STUFE_TON,
  objektLink,
  objektZeile,
  rueckgaengigKonflikt,
  zeitKurz,
} from "./kiAktivitaet";

const SEITENGROESSE = 50;

type StatusAuswahl = "alle" | "ausgefuehrt" | "rueckgaengig" | "fehlgeschlagen";
const STATUS_OPTIONEN: { wert: StatusAuswahl; label: string }[] = [
  { wert: "alle", label: "Alle" },
  { wert: "ausgefuehrt", label: "Ausgeführt" },
  { wert: "rueckgaengig", label: "Rückgängig" },
  { wert: "fehlgeschlagen", label: "Fehlgeschlagen" },
];

function StufeAbzeichen({ stufe }: { stufe: 1 | 2 | 3 }) {
  return (
    <span
      title={KI_STUFE_LABEL[stufe]}
      aria-label={KI_STUFE_LABEL[stufe]}
      className={`inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1 text-meta font-semibold ${STATUS_PILLE_KLASSE[KI_STUFE_TON[stufe]]}`}
    >
      {stufe}
    </span>
  );
}

function ObjektLink({ typ, id, label }: { typ: string; id: string; label: string }) {
  const ziel = objektLink({ typ, id, label });
  return ziel ? (
    <Link to={ziel} className="text-tint-text hover:underline">
      {label}
    </Link>
  ) : (
    <span>{label}</span>
  );
}

function AktionPanel({ aktion }: { aktion: KiAktion }) {
  const toast = useToast();
  const rueckgaengig = useKiRueckgaengig();
  const gruppen = gruppiereAenderungen(aktion.aenderungen);
  const konflikt = rueckgaengig.error ? rueckgaengigKonflikt(rueckgaengig.error) : null;

  function zuruecknehmen() {
    rueckgaengig.mutate(aktion.id, {
      onSuccess: () => toast.erfolg("Zurückgenommen"),
      onError: (err) => {
        if (rueckgaengigKonflikt(err)) return;
        toast.fehler(err instanceof Error && err.message ? err.message : "Zurücknehmen fehlgeschlagen.");
      },
    });
  }

  return (
    <div className="space-y-4 pt-3">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPille status={KI_STATUS_TON[aktion.status]} label={KI_STATUS_LABEL[aktion.status]} />
          <ClaudeMarke label="per KI" klein />
        </div>
        <h2 className="ap-heading text-titel-desktop font-semibold text-label">{aktion.zusammenfassung}</h2>
        <p className="text-sekundaer text-label2">
          von {aktion.user_name} über {aktion.client_name ?? "Claude"} · {datumUhrzeit(aktion.erstellt_am)}
        </p>
      </div>

      {aktion.status === "rueckgaengig" && (
        <Hinweiskasten ton="info">
          <p>
            Zurückgenommen{aktion.rueckgaengig_von_name ? ` von ${aktion.rueckgaengig_von_name}` : ""}
            {aktion.rueckgaengig_am ? ` am ${datumUhrzeit(aktion.rueckgaengig_am)}` : ""}.
          </p>
        </Hinweiskasten>
      )}

      {aktion.fehler && (
        <Hinweiskasten ton="fehler" titel="Fehler">
          <p>{aktion.fehler}</p>
        </Hinweiskasten>
      )}

      {gruppen.length > 0 && (
        <section aria-label="Änderungen" className="space-y-2">
          <h3 className="text-meta font-semibold tracking-wide text-label2 uppercase">Änderungen</h3>
          {gruppen.map((g) => (
            <div key={g.schluessel} className="rounded-[var(--radius-ap-md)] bg-fill p-3 text-fliess">
              <p className="mb-1 font-semibold text-label">
                <ObjektLink typ={g.zeilen[0].typ} id={g.zeilen[0].id} label={g.label} />
              </p>
              <ul className="space-y-1">
                {g.zeilen.map((z) => (
                  <li key={z.feld} className="flex flex-wrap items-baseline gap-x-2 text-sekundaer">
                    <span className="text-label2">{z.feld_label}</span>
                    <span className="text-label2 line-through">{z.vorher ?? "leer"}</span>
                    <span aria-hidden="true">→</span>
                    <span className="font-semibold text-label">{z.nachher ?? "leer"}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {aktion.erzeugt.length > 0 && (
        <section aria-label="Angelegt" className="space-y-1">
          <h3 className="text-meta font-semibold tracking-wide text-label2 uppercase">Angelegt</h3>
          <ul className="space-y-0.5 text-fliess">
            {aktion.erzeugt.map((r) => (
              <li key={`${r.typ}:${r.id}`}>
                <ObjektLink {...r} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {aktion.ziele.length > 0 && (
        <section aria-label="Betrifft" className="space-y-1">
          <h3 className="text-meta font-semibold tracking-wide text-label2 uppercase">Betrifft</h3>
          <ul className="space-y-0.5 text-fliess">
            {aktion.ziele.map((r) => (
              <li key={`${r.typ}:${r.id}`}>
                <ObjektLink {...r} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {konflikt && (
        <Hinweiskasten ton="warnung" titel="Zurücknehmen nicht möglich">
          <p>{konflikt.meldung}</p>
          {konflikt.konflikte.length > 0 && (
            <ul className="list-disc pl-4">
              {konflikt.konflikte.map((k, i) => (
                <li key={i}>
                  {k.label} · {k.feld_label}: erwartet {k.erwartet_anzeige ?? "leer"}, jetzt {k.aktuell_anzeige ?? "leer"}
                </li>
              ))}
            </ul>
          )}
        </Hinweiskasten>
      )}

      {aktion.rueckgaengig_moeglich && (
        <div className="space-y-1">
          <button
            type="button"
            className="btn-ap inline-flex h-9 items-center gap-1.5 px-3 text-sekundaer font-semibold"
            disabled={rueckgaengig.isPending}
            onClick={zuruecknehmen}
          >
            <Undo2 size={14} aria-hidden="true" /> {rueckgaengig.isPending ? "Nehme zurück …" : "Rückgängig"}
          </button>
          {aktion.rueckgaengig_bis && (
            <p className="text-sekundaer text-label2">möglich bis {datumUhrzeit(aktion.rueckgaengig_bis)}</p>
          )}
        </div>
      )}
    </div>
  );
}

/** Office-Liste aller Aktionen, die Claude im Namen von Mitarbeitern ausgeführt hat (Admin: alle, sonst eigene). */
export function OfficeKiAktivitaetPage() {
  const { currentUser } = useAuth();
  const istAdmin = currentUser?.role === "mandant_admin";
  const [params, setParams] = useSearchParams();
  const statusParam = params.get("status");
  const status: StatusAuswahl = STATUS_OPTIONEN.some((o) => o.wert === statusParam) ? (statusParam as StatusAuswahl) : "alle";
  const [offset, setOffset] = useState(0);
  const [auswahlId, setAuswahlId] = useState<string | null>(null);
  const breit = useMediaQuery("(min-width: 1280px)");

  const nutzer = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: istAdmin });

  const felder = useMemo<FilterFeld<unknown>[]>(
    () => [
      ...(istAdmin
        ? [
            {
              key: "mitarbeiter",
              label: "Mitarbeiter",
              typ: "person" as const,
              icon: UserIcon,
              operatoren: ["ist" as const],
              einzelwert: true,
              optionen: (nutzer.data ?? []).map((u) => ({ wert: u.id, label: u.name })),
            },
          ]
        : []),
      { key: "zeit", label: "Zeitraum", typ: "datum", icon: CalendarDays, operatoren: ["am", "vor", "nach", "zwischen", "relativ"] },
    ],
    [istAdmin, nutzer.data],
  );
  const zustand = useFilterZustand({ felder });

  // Standardzeitraum nur beim ersten Öffnen ohne eigene Filter/Suche in der URL; wer die Pille entfernt, bekommt sie nicht zurück.
  // Geladen wird erst, wenn die Pille in der URL steht, sonst ginge zuerst eine ungefilterte Anfrage raus.
  const [wartetAufStandard, setWartetAufStandard] = useState(() => zustand.bedingungen.length === 0 && !zustand.suche);
  const standardGesetzt = useRef(false);
  useEffect(() => {
    if (!wartetAufStandard) return;
    if (zustand.bedingungen.length > 0) {
      setWartetAufStandard(false);
    } else if (!standardGesetzt.current) {
      standardGesetzt.current = true;
      zustand.hinzufuegen({ feld: "zeit", op: "relativ", wert: { relativ: "letzte_7" } });
    }
  }, [wartetAufStandard, zustand]);
  const bereit = !wartetAufStandard;

  const erster = (b: { wert?: unknown }) => (Array.isArray(b.wert) ? (b.wert[0] as string | undefined) : undefined);
  const serverFilter = zuServerParametern(zustand.bedingungen, {
    mitarbeiter: (b): Record<string, string> => (istAdmin && erster(b) ? { user_id: erster(b)! } : {}),
    zeit: datumServerParameter,
  });
  const filter: KiAktionenFilter = {
    ...serverFilter,
    ...(status !== "alle" ? { status } : {}),
    ...(zustand.sucheVerzoegert ? { q: zustand.sucheVerzoegert } : {}),
  };
  const filterSchluessel = JSON.stringify(filter);
  useEffect(() => setOffset(0), [filterSchluessel]);
  const filterAktiv = zustand.bedingungen.length > 0 || !!zustand.suche || status !== "alle";

  const liste = useKiAktionenListe(filter, SEITENGROESSE, offset, bereit);
  const daten = liste.data;
  const zeile = daten?.eintraege.find((e) => e.id === auswahlId);
  const detail = useKiAktion(auswahlId, zeile);
  const aktion = detail.data ?? zeile ?? null;

  function statusSetzen(neu: StatusAuswahl) {
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        if (neu === "alle") n.delete("status");
        else n.set("status", neu);
        return n;
      },
      { replace: true },
    );
  }

  const tabelle = !daten ? (
    liste.isError ? (
      <FehlerZustand fehler={liste.error} was="Die KI-Aktivität" onErneut={() => void liste.refetch()} />
    ) : (
      <SkeletonList count={6} />
    )
  ) : daten.eintraege.length === 0 ? (
    <Karte className="p-4">
      <EmptyState
        icon={Sparkles}
        text={filterAktiv ? "Keine Treffer für diese Filter" : "Noch keine KI-Aktivität. Aktionen von Claude erscheinen hier."}
        action={
          filterAktiv ? (
            <button
              type="button"
              onClick={() => {
                zustand.zuruecksetzen();
                statusSetzen("alle");
              }}
              className="btn-ap h-9 px-3 text-sekundaer"
            >
              Filter zurücksetzen
            </button>
          ) : undefined
        }
      />
    </Karte>
  ) : (
    <TabellenRahmen>
      <table className="w-full text-left text-fliess">
        <caption className="sr-only">KI-Aktionen, neueste zuerst</caption>
        <thead className="bg-fill text-meta tracking-wide text-label2 uppercase">
          <tr>
            <th scope="col" className="px-3 py-2">Zeit</th>
            <th scope="col" className="px-3 py-2">Mitarbeiter</th>
            <th scope="col" className="px-3 py-2">Aktion</th>
            <th scope="col" className="px-3 py-2">Stufe</th>
            <th scope="col" className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {daten.eintraege.map((e) => {
            const aktiv = e.id === auswahlId;
            const objekte = objektZeile(e.ziele, e.erzeugt);
            return (
              <tr
                key={e.id}
                onClick={() => setAuswahlId(e.id)}
                className={`cursor-pointer border-t border-sep align-top ${aktiv ? "bg-tintbg" : "hover:bg-fill"}`}
              >
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-label2">{zeitKurz(e.erstellt_am)}</td>
                <td className="px-3 py-2 text-label">{e.user_name}</td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    onClick={() => setAuswahlId(e.id)}
                    aria-pressed={aktiv}
                    className="block text-left font-semibold text-label"
                  >
                    {e.zusammenfassung}
                  </button>
                  {objekte && <span className="block text-sekundaer text-label2">{objekte}</span>}
                </td>
                <td className="px-3 py-2">
                  <StufeAbzeichen stufe={e.stufe} />
                </td>
                <td className="px-3 py-2">
                  <StatusPille status={KI_STATUS_TON[e.status as KiAktionStatus]} label={KI_STATUS_LABEL[e.status as KiAktionStatus]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TabellenRahmen>
  );

  const liste_ = (
    <div className="space-y-3">
      {tabelle}
      {daten && daten.gesamt > 0 && (
        <div className="flex items-center justify-between text-sekundaer text-label2">
          <span>{seitenText(offset, daten.eintraege.length, daten.gesamt)}</span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - SEITENGROESSE))}
            >
              <ChevronLeft size={14} aria-hidden="true" /> Neuere
            </button>
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer"
              disabled={offset + SEITENGROESSE >= daten.gesamt}
              onClick={() => setOffset(offset + SEITENGROESSE)}
            >
              Ältere <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-[1400px]">
      <SeitenKopf titel="KI-Aktivität" untertitel="Alles, was Claude im Namen von Mitarbeitern getan hat" />
      <div className="mb-3 space-y-2">
        <SegmentedControl ariaLabel="Status" optionen={STATUS_OPTIONEN} wert={status} onChange={statusSetzen} />
        <FilterLeiste felder={felder} zustand={zustand} variante="office" suchPlatzhalter="Aktionen suchen…" />
      </div>
      <ListeMitPanel
        liste={liste_}
        panel={aktion ? <AktionPanel key={aktion.id} aktion={aktion} /> : null}
        panelTitel="KI-Aktion"
        onSchliessen={() => setAuswahlId(null)}
        nurPanel={!breit}
      />
    </div>
  );
}
