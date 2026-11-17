import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, CircleDot, Download, Eye, FileDown, ListTree, Network, UserSquare } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { accountTypenApi, organigrammApi, rechteApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { useAuth } from "../../context/AuthContext";
import type { RechteAktion } from "../../types";
import type { Position, PositionCreate } from "../../types/organigramm";
import { AnsichtUmschalter, SeitenKopf } from "../OfficeUi";
import { AnzeigenAlsDialog } from "./AnzeigenAlsDialog";
import {
  kontextAktionen,
  menueNachOeffnen,
  besetzungText,
  POSITION_STATUS_LABEL,
  POSITION_STATUS_TOKEN,
  verstaendlicherFehler,
  type AnlegeModus,
  type KontextAktion,
} from "./darstellung";
import { csvDateiname, csvHerunterladen, positionenCsv } from "./export";
import { alleMitKindern, standardEingeklappt, type LayoutKnoten } from "./layout";
import {
  listenZeilen,
  sortiereZeilen,
  trefferMitVorfahren,
  type SortRichtung,
  type SortSchluessel,
} from "./liste";
import { OrganigrammDiagramm } from "./OrganigrammDiagramm";
import { OrganigrammDruck, OrganigrammListe } from "./OrganigrammListe";
import { PositionAnlegenSheet } from "./PositionAnlegenSheet";
import { PositionKontextMenue } from "./PositionKontextMenue";
import { PositionPanel, type PanelTab } from "./PositionPanel";
import { useBestaetigung } from "../../components/ConfirmDialog";

type Ansicht = "diagramm" | "liste";

const STATUS_OPTIONEN = (["besetzt", "vakant", "geplant"] as const).map((s) => ({
  wert: s,
  label: POSITION_STATUS_LABEL[s],
  status: POSITION_STATUS_TOKEN[s],
}));

export function OrganigrammPage() {
  const bestaetigen = useBestaetigung();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const darf = useCallback((aktion: string) => hatRecht("organigramm", aktion as RechteAktion), [hatRecht]);
  const darfPersonen = hatRecht("mitarbeiterverwaltung", "sehen");

  const [ansicht, setAnsicht] = useState<Ansicht>("diagramm");
  const [eingeklappt, setEingeklappt] = useState<Set<string> | null>(null);
  const [panel, setPanel] = useState<{ id: string; tab: PanelTab } | null>(null);
  const [menue, setMenue] = useState<{ position: Position; anker: { x: number; y: number } } | null>(null);
  const [anlegen, setAnlegen] = useState<{ modus: AnlegeModus; parent: Position } | null>(null);
  const [anlegenFehler, setAnlegenFehler] = useState<string | null>(null);
  const [anzeigenAls, setAnzeigenAls] = useState<{ positionId: string | null } | null>(null);
  const [meldung, setMeldung] = useState<{ art: "fehler" | "info"; text: string } | null>(null);
  const [sortierung, setSortierung] = useState<{ schluessel: SortSchluessel; richtung: SortRichtung }>({ schluessel: "baum", richtung: "auf" });
  const [drucken, setDrucken] = useState(false);

  const { data: registry } = useQuery({ queryKey: ["rechte-registry"], queryFn: rechteApi.registry, staleTime: 5 * 60 * 1000 });
  const { data: positionen, isLoading, error, refetch } = useQuery({ queryKey: ["org-positionen"], queryFn: () => organigrammApi.positionen() });
  const { data: orgEinheiten } = useQuery({ queryKey: ["org-einheiten"], queryFn: organigrammApi.orgEinheiten });
  // Die Account-Typen-API ist Verwaltern vorbehalten; ohne dieses Recht reichen die Namen aus den Positionen.
  const { data: accountTypen } = useQuery({
    queryKey: ["account-typen"],
    queryFn: accountTypenApi.list,
    enabled: darf("rechte_verwalten"),
  });

  const alle = useMemo(() => positionen ?? [], [positionen]);
  const felder = useMemo<FilterFeld<Position>[]>(
    () => [
      { key: "titel", label: "Position", typ: "text", icon: Network, wert: (p) => p.titel },
      { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, wert: (p) => p.status, optionen: STATUS_OPTIONEN },
      {
        key: "einheit",
        label: "Einheit",
        typ: "verknuepfung",
        icon: Building2,
        wert: (p) => p.org_einheit?.id,
        optionen: (orgEinheiten ?? []).map((o) => ({ wert: o.id, label: o.name })),
      },
      { key: "person", label: "Besetzung", typ: "text", icon: UserSquare, wert: (p) => besetzungText(p) },
    ],
    [orgEinheiten],
  );
  const zustand = useFilterZustand({ felder });
  const aktiv = zustand.aktiveAnzahl > 0 || zustand.sucheVerzoegert.trim() !== "";
  // Treffer im Baum plus Vorfahren (Pfad bleibt sichtbar); Kontext-Positionen sind nie Treffer.
  const filterErgebnis = useMemo(() => {
    if (!aktiv) {
      const ids = new Set(alle.map((p) => p.id));
      return { treffer: ids, sichtbar: ids };
    }
    const kandidaten = alle.filter((p) => !p.kontext);
    const gefunden = sucheAnwenden(
      filterAnwenden(kandidaten, zustand.bedingungen, felder),
      zustand.sucheVerzoegert,
      (p) => [p.titel, p.org_einheit?.name, p.account_typ?.name, besetzungText(p), p.status ? POSITION_STATUS_LABEL[p.status] : ""].join(" "),
    );
    const treffer = new Set(gefunden.map((p) => p.id));
    return { treffer, sichtbar: trefferMitVorfahren(alle, treffer) };
  }, [alle, aktiv, zustand.bedingungen, zustand.sucheVerzoegert, felder]);

  const standard = useMemo(() => {
    const knoten: LayoutKnoten[] = alle.map((p) => ({ id: p.id, parentId: p.parent_id, typ: p.typ }));
    return standardEingeklappt(knoten, 3);
  }, [alle]);
  const eingeklapptWirksam = eingeklappt ?? standard;

  const kinderAnzahl = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of alle) if (p.parent_id) m.set(p.parent_id, (m.get(p.parent_id) ?? 0) + 1);
    return m;
  }, [alle]);

  const zeilen = useMemo(() => {
    const baum = listenZeilen(alle).filter((z) => (aktiv ? filterErgebnis.treffer.has(z.position.id) : true));
    return sortiereZeilen(baum, sortierung.schluessel, sortierung.richtung);
  }, [alle, aktiv, filterErgebnis, sortierung]);

  const aufklappen = (id: string | null) => {
    if (!id) return;
    setEingeklappt((alt) => {
      const basis = new Set(alt ?? standard);
      basis.delete(id);
      return basis;
    });
  };

  const neuLaden = () => {
    queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
    queryClient.invalidateQueries({ queryKey: ["org-position"] });
  };
  const fehlschlag = (fallback: string) => (err: unknown) => setMeldung({ art: "fehler", text: verstaendlicherFehler(err, fallback) });

  const umhaengen = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string; titel: string; zielTitel: string }) =>
      organigrammApi.updatePosition(id, { parent_id: parentId }),
    onSuccess: (_, v) => {
      setMeldung({ art: "info", text: `„${v.titel}“ wurde unter „${v.zielTitel}“ umgehängt.` });
      aufklappen(v.parentId);
      neuLaden();
    },
    // Das Diagramm setzt die Knoten ohnehin auf das berechnete Layout zurueck.
    onError: fehlschlag("Umhängen fehlgeschlagen"),
  });

  const erstellen = useMutation({
    mutationFn: (body: PositionCreate) => organigrammApi.createPosition(body),
    onSuccess: (_, body) => {
      setAnlegen(null);
      setAnlegenFehler(null);
      aufklappen(body.parent_id);
      neuLaden();
    },
    onError: (err) => setAnlegenFehler(verstaendlicherFehler(err, "Anlegen fehlgeschlagen")),
  });

  const duplizieren = useMutation({
    mutationFn: (id: string) => organigrammApi.duplizieren(id),
    onSuccess: neuLaden,
    onError: fehlschlag("Duplizieren fehlgeschlagen"),
  });
  const archivieren = useMutation({
    mutationFn: (id: string) => organigrammApi.archivieren(id),
    onSuccess: () => {
      setPanel(null);
      neuLaden();
    },
    onError: fehlschlag("Archivieren fehlgeschlagen"),
  });
  const loeschen = useMutation({
    mutationFn: (id: string) => organigrammApi.loeschen(id),
    onSuccess: () => {
      setPanel(null);
      neuLaden();
    },
    onError: fehlschlag("Löschen fehlgeschlagen"),
  });

  const umschalten = useCallback(
    (id: string) =>
      setEingeklappt((alt) => {
        const basis = new Set(alt ?? standard);
        if (basis.has(id)) basis.delete(id);
        else basis.add(id);
        return basis;
      }),
    [standard],
  );
  const waehlen = useCallback((id: string) => setPanel({ id, tab: "stammdaten" }), []);
  const menueOeffnen = useCallback(
    (position: Position, anker: { x: number; y: number }, umschalten?: boolean) =>
      setMenue((alt) => menueNachOeffnen(alt, position, anker, umschalten)),
    [],
  );
  const umhaengenAnfordern = useCallback(
    async (id: string, parentId: string) => {
      const q = alle.find((p) => p.id === id);
      const z = alle.find((p) => p.id === parentId);
      if (q && z) umhaengen.mutate({ id, parentId, titel: q.titel, zielTitel: z.titel });
    },
    [alle, umhaengen],
  );
  const ungueltigerDrop = useCallback((text: string) => setMeldung({ art: "fehler", text }), []);

  async function menueAktion(aktion: KontextAktion, p: Position) {
    setMenue(null);
    switch (aktion) {
      case "details":
        setPanel({ id: p.id, tab: "stammdaten" });
        break;
      case "rechte":
        setPanel({ id: p.id, tab: "rechte" });
        break;
      case "darunter":
      case "platzhalter":
      case "stabsstelle":
        setAnlegenFehler(null);
        setAnlegen({ modus: aktion, parent: p });
        break;
      case "duplizieren":
        duplizieren.mutate(p.id);
        break;
      case "anzeigen_als":
        setAnzeigenAls({ positionId: p.id });
        break;
      case "archivieren":
        if (await bestaetigen({ titel: `Position „${p.titel}“ archivieren?`, text: `Sie verschwindet aus dem Organigramm, die Historie bleibt erhalten.`, bestaetigenLabel: "Archivieren" })) archivieren.mutate(p.id);
        break;
      case "loeschen":
        if (await bestaetigen({ titel: `Position „${p.titel}“ endgültig löschen?`, text: `Das kann nicht rückgängig gemacht werden.`, bestaetigenLabel: "Endgültig löschen" })) loeschen.mutate(p.id);
        break;
    }
  }

  const sortieren = (schluessel: SortSchluessel) =>
    setSortierung((alt) => ({
      schluessel,
      richtung: alt.schluessel === schluessel && alt.richtung === "auf" ? "ab" : "auf",
    }));

  const anzahl = aktiv ? filterErgebnis.treffer.size : alle.filter((p) => !p.kontext).length;

  return (
    <div>
      <SeitenKopf titel="Organigramm" anzahl={anzahl}>
        <AnsichtUmschalter<Ansicht>
          wert={ansicht}
          onWechsel={setAnsicht}
          optionen={[
            { wert: "diagramm", label: "Diagramm", icon: Network },
            { wert: "liste", label: "Liste", icon: ListTree },
          ]}
        />
        <button type="button" className="btn-ap" onClick={() => setAnzeigenAls({ positionId: null })}>
          <Eye size={14} strokeWidth={2} aria-hidden="true" />
          Anzeigen als …
        </button>
        <button type="button" className="btn-ap" onClick={() => csvHerunterladen(positionenCsv(zeilen), csvDateiname())} disabled={zeilen.length === 0}>
          <Download size={14} strokeWidth={2} aria-hidden="true" />
          CSV
        </button>
        <button type="button" className="btn-ap" onClick={() => setDrucken(true)} disabled={zeilen.length === 0}>
          <FileDown size={14} strokeWidth={2} aria-hidden="true" />
          PDF
        </button>
      </SeitenKopf>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FilterLeiste
          felder={felder}
          zustand={zustand}
          variante="office"
          suchPlatzhalter="Position, Einheit oder Person suchen…"
          className="min-w-0 flex-1"
        />
        {ansicht === "diagramm" && (
          <div className="ml-auto flex gap-2">
            <button type="button" className="btn-ap" onClick={() => setEingeklappt(new Set())} disabled={aktiv}>
              Alles aufklappen
            </button>
            <button
              type="button"
              className="btn-ap"
              onClick={() => setEingeklappt(alleMitKindern(alle.map((p) => ({ id: p.id, parentId: p.parent_id, typ: p.typ }))))}
              disabled={aktiv}
            >
              Alles zuklappen
            </button>
          </div>
        )}
      </div>

      {meldung && (
        <div
          role={meldung.art === "fehler" ? "alert" : "status"}
          className={`mb-3 flex items-start justify-between gap-3 rounded-[10px] px-3 py-2 text-fliess ${
            meldung.art === "fehler" ? "bg-st-fehlt-bg text-st-fehlt" : "bg-st-erledigt-bg text-st-erledigt"
          }`}
        >
          <span>{meldung.text}</span>
          <button type="button" onClick={() => setMeldung(null)} className="shrink-0 font-semibold underline">
            Schließen
          </button>
        </div>
      )}

      {error ? (
        <FehlerZustand fehler={error} was="Das Organigramm" onErneut={() => void refetch()} />
      ) : isLoading ? (
        <SkeletonList count={5} />
      ) : alle.length === 0 ? (
        <EmptyState icon={Network} text="Noch keine Positionen im Organigramm – oder Sie haben keinen Zugriff auf einen Bereich." />
      ) : ansicht === "diagramm" ? (
        <>
          {aktiv && filterErgebnis.treffer.size === 0 ? (
            <EmptyState
              icon={Network}
              text={zustand.sucheVerzoegert && zustand.bedingungen.length === 0 ? `Nichts gefunden für „${zustand.sucheVerzoegert}“` : "Keine Treffer für diese Filter"}
              action={
                <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
                  Filter zurücksetzen
                </button>
              }
            />
          ) : (
            <div className="card-ap h-[calc(100vh-250px)] min-h-[460px] overflow-hidden" data-testid="org-diagramm">
              <OrganigrammDiagramm
                positionen={alle}
                sichtbar={filterErgebnis.sichtbar}
                treffer={filterErgebnis.treffer}
                filterAktiv={aktiv}
                eingeklappt={eingeklapptWirksam}
                ausgewaehltId={panel?.id ?? null}
                darfUmhaengen={darf("bearbeiten")}
                onWaehlen={waehlen}
                onMenue={menueOeffnen}
                onUmschalten={umschalten}
                onUmhaengen={umhaengenAnfordern}
                onUngueltigerDrop={ungueltigerDrop}
              />
            </div>
          )}
          <p className="mt-2 text-sekundaer text-label2">
            Zum Umhängen eine Position auf die neue übergeordnete Position ziehen. Rechtsklick oder „…“ öffnet die Aktionen. Gestrichelte
            Verbindungen führen zu Stabsstellen.
          </p>
        </>
      ) : (
        <OrganigrammListe
          zeilen={zeilen}
          sortierung={sortierung.schluessel}
          richtung={sortierung.richtung}
          onSortieren={sortieren}
          onWaehlen={waehlen}
          onMenue={menueOeffnen}
          ausgewaehltId={panel?.id ?? null}
        />
      )}

      {menue && (
        <PositionKontextMenue
          anker={menue.anker}
          aktionen={kontextAktionen(menue.position, darf, kinderAnzahl.get(menue.position.id) ?? 0)}
          onWahl={(a) => menueAktion(a, menue.position)}
          onClose={() => setMenue(null)}
        />
      )}

      {panel && (
        <PositionPanel
          positionId={panel.id}
          startTab={panel.tab}
          registry={registry}
          orgEinheiten={orgEinheiten ?? []}
          accountTypen={accountTypen ?? []}
          darf={darf}
          onClose={() => setPanel(null)}
          onAnzeigenAls={(id) => setAnzeigenAls({ positionId: id })}
        />
      )}

      {anlegen && (
        <PositionAnlegenSheet
          modus={anlegen.modus}
          parent={anlegen.parent}
          accountTypen={accountTypen ?? []}
          orgEinheiten={orgEinheiten ?? []}
          darfRechteVerwalten={darf("rechte_verwalten")}
          pending={erstellen.isPending}
          fehler={anlegenFehler}
          onClose={() => setAnlegen(null)}
          onAnlegen={(body) => erstellen.mutate(body)}
        />
      )}

      {anzeigenAls && (
        <AnzeigenAlsDialog
          startPositionId={anzeigenAls.positionId}
          positionen={alle}
          registry={registry}
          accountTypen={accountTypen ?? []}
          darfPersonen={darfPersonen}
          onClose={() => setAnzeigenAls(null)}
        />
      )}

      {drucken && <OrganigrammDruck zeilen={zeilen} onFertig={() => setDrucken(false)} />}
    </div>
  );
}
