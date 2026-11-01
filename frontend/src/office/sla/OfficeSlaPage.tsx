import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Timer, Trash2 } from "lucide-react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { slaApi } from "../../api/endpoints";
import { FehlerMeldung } from "../../components/Hinweiskasten";
import { IconBadge } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import { LEISTUNGSTYP_LABEL } from "../../config/vorgangDarstellung";
import { Karte, SeitenKopf } from "../OfficeUi";
import {
  NEUE_RICHTLINIE,
  WOCHENTAGE,
  dauerText,
  fensterAus,
  minutenOderLeer,
  zeitenAus,
  type SlaFristAuswertung,
  type SlaRichtlinie,
  type SlaRichtlinieEingabe,
  type SlaStufe,
} from "./slaUtils";

const PRIORITAETEN = ["1", "2", "3", "4", "5"];

function fehlerText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Unerwarteter Fehler – bitte erneut versuchen.";
}

function FristZeile({ titel, daten }: { titel: string; daten: SlaFristAuswertung }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-5">
      <span className="font-semibold text-label">{titel}</span>
      <span className="text-label2">
        Quote: <b className="text-label">{daten.quote_prozent != null ? `${daten.quote_prozent} %` : "—"}</b>
      </span>
      <span className="text-label2">
        erfüllt / verletzt: <b className="text-label">{daten.erfuellt} / {daten.verletzt}</b>
      </span>
      <span className="text-label2">
        Median: <b className="text-label">{dauerText(daten.median_minuten != null ? Math.round(daten.median_minuten) : null)}</b>
      </span>
      <span className="text-label2">
        P90: <b className="text-label">{dauerText(daten.p90_minuten != null ? Math.round(daten.p90_minuten) : null)}</b>
      </span>
    </div>
  );
}

function AuswertungKarte() {
  const zeitraum = useMemo(() => {
    const bis = new Date();
    const von = new Date(bis.getTime() - 30 * 86_400_000);
    return { von: von.toISOString(), bis: bis.toISOString() };
  }, []);
  const abfrage = useQuery({
    queryKey: ["sla-auswertung", zeitraum.von.slice(0, 10)],
    queryFn: () => slaApi.auswertung(zeitraum.von, zeitraum.bis),
  });
  return (
    <Karte className="space-y-3 p-5">
      <h2 className="ap-heading text-lg font-semibold text-label">Erfüllung der letzten 30 Tage</h2>
      {abfrage.isError && <FehlerMeldung meldung={fehlerText(abfrage.error)} />}
      {abfrage.data && abfrage.data.vorgaenge === 0 && (
        <p className="text-sm text-label2">Noch keine Vorgänge mit SLA im Zeitraum.</p>
      )}
      {abfrage.data && abfrage.data.vorgaenge > 0 && (
        <>
          <p className="text-sm text-label2">{abfrage.data.vorgaenge} Vorgänge mit SLA</p>
          <FristZeile titel="Reaktion" daten={abfrage.data.reaktion} />
          <FristZeile titel="Lösung" daten={abfrage.data.loesung} />
        </>
      )}
    </Karte>
  );
}

function Editor({
  start,
  speichern,
  abbrechen,
  fehler,
  laeuft,
}: {
  start: SlaRichtlinieEingabe;
  speichern: (r: SlaRichtlinieEingabe) => void;
  abbrechen: () => void;
  fehler: string | null;
  laeuft: boolean;
}) {
  const [r, setR] = useState<SlaRichtlinieEingabe>(start);
  const fenster = fensterAus(r.geschaeftszeiten);
  const [regelTyp, setRegelTyp] = useState("stoerung");

  const setZiel = (prio: string, feld: "reaktion_min" | "loesung_min", text: string) =>
    setR((alt) => ({ ...alt, ziele: { ...alt.ziele, [prio]: { ...alt.ziele[prio], [feld]: minutenOderLeer(text) ?? null } } }));
  const setStufe = (i: number, teil: Partial<SlaStufe>) =>
    setR((alt) => ({ ...alt, stufen: alt.stufen.map((s, j) => (j === i ? { ...s, ...teil } : s)) }));

  function absenden() {
    const ziele = Object.fromEntries(
      Object.entries(r.ziele).filter(([, z]) => z.reaktion_min != null || z.loesung_min != null),
    );
    speichern({ ...r, ziele });
  }

  return (
    <Karte className="space-y-5 p-5">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor="sla-name" className="mb-1 block text-xs font-semibold text-label2">Name</label>
          <input id="sla-name" className="field-ap w-full" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} />
        </div>
        <div>
          <label htmlFor="sla-kalender" className="mb-1 block text-xs font-semibold text-label2">Geltungszeit</label>
          <select
            id="sla-kalender"
            className="field-ap w-full"
            value={r.kalender}
            onChange={(e) => {
              const kalender = e.target.value as SlaRichtlinieEingabe["kalender"];
              setR({ ...r, kalender, geschaeftszeiten: kalender === "geschaeftszeiten" ? zeitenAus(fenster.tage, fenster.von, fenster.bis) : {} });
            }}
          >
            <option value="rund_um_die_uhr">Rund um die Uhr (24/7)</option>
            <option value="geschaeftszeiten">Nur Geschäftszeiten</option>
          </select>
        </div>
      </div>

      {r.kalender === "geschaeftszeiten" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Wochentage">
            {WOCHENTAGE.map((tag, i) => (
              <label key={tag} className="flex items-center gap-1 text-sm text-label">
                <input
                  type="checkbox"
                  checked={fenster.tage.includes(i)}
                  onChange={(e) => {
                    const tage = e.target.checked ? [...fenster.tage, i] : fenster.tage.filter((t) => t !== i);
                    setR({ ...r, geschaeftszeiten: zeitenAus(tage, fenster.von, fenster.bis) });
                  }}
                />
                {tag}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-label2">
            von
            <input type="time" className="field-ap" aria-label="Beginn" value={fenster.von}
              onChange={(e) => setR({ ...r, geschaeftszeiten: zeitenAus(fenster.tage, e.target.value, fenster.bis) })} />
            bis
            <input type="time" className="field-ap" aria-label="Ende" value={fenster.bis}
              onChange={(e) => setR({ ...r, geschaeftszeiten: zeitenAus(fenster.tage, fenster.von, e.target.value) })} />
            <label className="ml-2 flex items-center gap-1">
              <input type="checkbox" checked={r.feiertage_ausnehmen} onChange={(e) => setR({ ...r, feiertage_ausnehmen: e.target.checked })} />
              Feiertage ausnehmen
            </label>
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-label">Fristen je Priorität (Minuten, leer = keine Frist)</h3>
        <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-2 text-sm">
          <span />
          <span className="text-xs font-semibold text-label2">Reaktion</span>
          <span className="text-xs font-semibold text-label2">Lösung</span>
          {PRIORITAETEN.map((p) => (
            <div key={p} className="contents">
              <span className="text-label">Prio {p}</span>
              <input className="field-ap" inputMode="numeric" aria-label={`Reaktion Prio ${p}`}
                value={r.ziele[p]?.reaktion_min ?? ""} onChange={(e) => setZiel(p, "reaktion_min", e.target.value)} />
              <input className="field-ap" inputMode="numeric" aria-label={`Lösung Prio ${p}`}
                value={r.ziele[p]?.loesung_min ?? ""} onChange={(e) => setZiel(p, "loesung_min", e.target.value)} />
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-label">Automatische Priorität</h3>
        <p className="mb-2 text-xs text-label2">Hebt die Priorität neuer Vorgänge dieses Leistungstyps an, senkt sie nie.</p>
        <ul className="mb-2 space-y-1">
          {Object.entries(r.prioritaet_regeln).map(([typ, prio]) => (
            <li key={typ} className="flex items-center gap-2 text-sm text-label">
              {LEISTUNGSTYP_LABEL[typ] ?? typ} → Prio {prio}
              <button type="button" aria-label={`Regel ${typ} entfernen`} className="text-label2"
                onClick={() => setR({ ...r, prioritaet_regeln: Object.fromEntries(Object.entries(r.prioritaet_regeln).filter(([t]) => t !== typ)) })}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <select className="field-ap" aria-label="Leistungstyp" value={regelTyp} onChange={(e) => setRegelTyp(e.target.value)}>
            {Object.entries(LEISTUNGSTYP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select id="sla-regel-prio" className="field-ap" aria-label="Priorität" defaultValue="5">
            {PRIORITAETEN.map((p) => <option key={p} value={p}>Prio {p}</option>)}
          </select>
          <button type="button" className="btn-ap-toolbar inline-flex h-9 items-center gap-1 px-3 text-sm"
            onClick={() => {
              const prio = Number((document.getElementById("sla-regel-prio") as HTMLSelectElement).value);
              setR({ ...r, prioritaet_regeln: { ...r.prioritaet_regeln, [regelTyp]: prio } });
            }}>
            <Plus size={14} aria-hidden="true" /> Regel
          </button>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-label">Eskalation</h3>
        <ul className="space-y-2">
          {r.stufen.map((s, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <select className="field-ap" aria-label="Fristart" value={s.frist_art} onChange={(e) => setStufe(i, { frist_art: e.target.value as SlaStufe["frist_art"] })}>
                <option value="reaktion">Reaktion</option>
                <option value="loesung">Lösung</option>
              </select>
              bei
              <input className="field-ap w-20" inputMode="numeric" aria-label="Schwelle in Prozent" value={s.schwelle_prozent}
                onChange={(e) => setStufe(i, { schwelle_prozent: minutenOderLeer(e.target.value) ?? 1 })} />
              % →
              <select className="field-ap" aria-label="Aktion" value={s.aktion} onChange={(e) => setStufe(i, { aktion: e.target.value as SlaStufe["aktion"] })}>
                <option value="benachrichtigen">Benachrichtigen</option>
                <option value="mail">E-Mail</option>
              </select>
              an
              <select className="field-ap" aria-label="Empfänger" value={s.empfaenger} onChange={(e) => setStufe(i, { empfaenger: e.target.value as SlaStufe["empfaenger"] })}>
                <option value="zugewiesener">Zugewiesener</option>
                <option value="dispo">Disposition</option>
                <option value="vorgesetzter">Vorgesetzter</option>
                <option value="admin">Administrator</option>
              </select>
              <button type="button" aria-label="Stufe entfernen" className="text-label2"
                onClick={() => setR({ ...r, stufen: r.stufen.filter((_, j) => j !== i) })}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="btn-ap-toolbar mt-2 inline-flex h-9 items-center gap-1 px-3 text-sm"
          onClick={() => setR({ ...r, stufen: [...r.stufen, { frist_art: "loesung", schwelle_prozent: 100, aktion: "benachrichtigen", empfaenger: "dispo" }] })}>
          <Plus size={14} aria-hidden="true" /> Stufe
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm text-label">
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={r.ist_standard} onChange={(e) => setR({ ...r, ist_standard: e.target.checked })} />
          Standard für alle Vorgänge ohne Vertrags-Richtlinie
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={r.aktiv} onChange={(e) => setR({ ...r, aktiv: e.target.checked })} />
          Aktiv
        </label>
      </div>

      {fehler && <FehlerMeldung meldung={fehler} alsKasten />}
      <div className="flex gap-2">
        <button type="button" className="btn-ap-primary h-9 px-4 text-sm font-semibold disabled:opacity-50"
          disabled={laeuft || !r.name.trim()} onClick={absenden}>
          Speichern
        </button>
        <button type="button" className="btn-ap-toolbar h-9 px-4 text-sm" onClick={abbrechen}>Abbrechen</button>
      </div>
    </Karte>
  );
}

export function OfficeSlaPage() {
  const { currentUser, hatRecht } = useAuth();
  const queryClient = useQueryClient();
  const [bearbeite, setBearbeite] = useState<{ id: string | null; daten: SlaRichtlinieEingabe } | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const liste = useQuery({ queryKey: ["sla-richtlinien"], queryFn: () => slaApi.richtlinien() });
  const speichern = useMutation({
    mutationFn: ({ id, daten }: { id: string | null; daten: SlaRichtlinieEingabe }) =>
      id ? slaApi.aendern(id, daten) : slaApi.anlegen(daten),
    onSuccess: () => {
      setFehler(null);
      setBearbeite(null);
      void queryClient.invalidateQueries({ queryKey: ["sla-richtlinien"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });
  const loeschen = useMutation({
    mutationFn: (id: string) => slaApi.loeschen(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sla-richtlinien"] }),
    onError: (err) => setFehler(fehlerText(err)),
  });

  if (currentUser && !hatRecht("sla", "sehen") && currentUser.role !== "mandant_admin") {
    return <Navigate to="/vorgaenge" replace />;
  }

  return (
    <div className="mx-auto max-w-[1000px] space-y-5">
      <SeitenKopf titel="SLA-Richtlinien" anzahl={liste.data?.length}>
        <button type="button" className="btn-ap-primary inline-flex h-9 items-center gap-2 px-4 text-sm font-semibold"
          onClick={() => setBearbeite({ id: null, daten: NEUE_RICHTLINIE })}>
          <Plus size={15} aria-hidden="true" /> Neue Richtlinie
        </button>
      </SeitenKopf>
      <p className="text-sm text-label2">
        Reaktions- und Lösungsfristen für Vorgänge, mit Eskalation bei drohender Überschreitung. Welche Richtlinie
        gilt, richtet sich nach dem Vertrag des Vorgangs, sonst nach dem Standard.
      </p>
      {liste.isError && <FehlerMeldung meldung={fehlerText(liste.error)} alsKasten />}
      {fehler && !bearbeite && <FehlerMeldung meldung={fehler} alsKasten />}

      {bearbeite && (
        <Editor
          key={bearbeite.id ?? "neu"}
          start={bearbeite.daten}
          fehler={fehler}
          laeuft={speichern.isPending}
          abbrechen={() => { setBearbeite(null); setFehler(null); }}
          speichern={(daten) => speichern.mutate({ id: bearbeite.id, daten })}
        />
      )}

      <div className="space-y-2">
        {(liste.data ?? []).map((r: SlaRichtlinie) => (
          <Karte key={r.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="flex items-center gap-3">
              <IconBadge icon={Timer} tone="amber" />
              <div>
                <div className="font-semibold text-label">
                  {r.name}
                  {r.ist_standard && <span className="ml-2 text-xs font-medium text-tint-text">Standard</span>}
                  {!r.aktiv && <span className="ml-2 text-xs font-medium text-label2">inaktiv</span>}
                </div>
                <div className="text-xs text-label2">
                  {r.kalender === "rund_um_die_uhr" ? "24/7" : "Geschäftszeiten"} · {Object.keys(r.ziele).length} Prioritäten ·{" "}
                  {r.stufen.length} Eskalationsstufen
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button type="button" className="btn-ap-toolbar h-8 px-3 text-sm"
                onClick={() => { setFehler(null); setBearbeite({ id: r.id, daten: { ...r } }); }}>
                Bearbeiten
              </button>
              <button type="button" className="btn-ap-toolbar h-8 px-3 text-sm" aria-label={`${r.name} löschen`}
                onClick={() => { if (window.confirm(`Richtlinie „${r.name}“ löschen?`)) loeschen.mutate(r.id); }}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          </Karte>
        ))}
        {liste.data?.length === 0 && <p className="text-sm text-label2">Noch keine Richtlinie angelegt.</p>}
      </div>

      <AuswertungKarte />
    </div>
  );
}
