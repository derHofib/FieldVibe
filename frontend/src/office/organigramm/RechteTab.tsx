import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { organigrammApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import type { AccountTyp } from "../../types";
import type { PositionDetail, RechteRegistry } from "../../types/organigramm";
import { aktionLabel, scopeLabel, verstaendlicherFehler } from "./darstellung";
import {
  aktionsSpalten,
  bereichKennt,
  herkunftTexte,
  overridesAusZustaenden,
  schluessel,
  scopeOptionen,
  vorlagenScopes,
  wertZuZustand,
  wirksamerScope,
  zellenArt,
  zustaendeAusOverrides,
  zustaendeGleich,
  zustandZuWert,
  ZELLEN_ART_LABEL,
  type ZellenArt,
  type ZellenZustand,
} from "./rechteMatrix";

const ART_KLASSE: Record<ZellenArt, string> = {
  vorlage_erlaubt: "border-sep text-label",
  vorlage_nein: "border-sep text-label3",
  zusaetzlich: "border-st-erledigt-dot text-st-erledigt",
  verweigert: "border-st-fehlt-dot text-st-fehlt",
};

const DIFF_LABEL = {
  hinzugefuegt: "Zusätzlich erlaubt",
  entfernt: "Entzogen",
  scope_geaendert: "Reichweite geändert",
} as const;

function Zelle({
  bereich,
  bereichLabel,
  aktion,
  registry,
  zustand,
  vorlage,
  herkunft,
  schreibgeschuetzt,
  onAendern,
}: {
  bereich: string;
  bereichLabel: string;
  aktion: string;
  registry: RechteRegistry;
  zustand: ZellenZustand;
  vorlage: ReturnType<typeof wirksamerScope>;
  herkunft: string[];
  schreibgeschuetzt: boolean;
  onAendern: (z: ZellenZustand) => void;
}) {
  const [info, setInfo] = useState<{ top: number; left: number } | null>(null);
  const art = zellenArt(zustand, vorlage);
  const wirksam = wirksamerScope(zustand, vorlage);
  const bezeichnung = `${aktionLabel(aktion)}: ${ZELLEN_ART_LABEL[art]}${wirksam ? `, ${scopeLabel(wirksam)}` : ""}`;

  return (
    <div className="relative flex items-center gap-1">
      <select
        aria-label={`${bereichLabel} – ${bezeichnung}`}
        value={zustandZuWert(zustand)}
        disabled={schreibgeschuetzt}
        onChange={(e) => onAendern(wertZuZustand(e.target.value))}
        className={`h-7 w-[112px] rounded-[7px] border bg-card px-1 text-xs disabled:opacity-70 ${ART_KLASSE[art]}`}
        title={bezeichnung}
      >
        <option value="vorlage">Vorlage: {vorlage ? scopeLabel(vorlage) : "–"}</option>
        {scopeOptionen(registry, bereich).map((s) => (
          <option key={s} value={`erlauben:${s}`}>
            Erlaubt: {scopeLabel(s)}
          </option>
        ))}
        <option value="verweigern">Verweigert</option>
      </select>
      <button
        type="button"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setInfo((v) => (v ? null : { top: r.bottom + 4, left: Math.max(8, Math.min(r.right - 224, window.innerWidth - 232)) }));
        }}
        onKeyDown={(e) => e.key === "Escape" && setInfo(null)}
        onBlur={() => setInfo(null)}
        aria-expanded={info !== null}
        aria-label={`Herkunft anzeigen: ${bereichLabel} ${aktionLabel(aktion)}`}
        title={herkunft.length > 0 ? herkunft.join("\n") : "Keine Herkunft (kein Recht)"}
        className="shrink-0 rounded-full p-0.5 text-label2 hover:text-label"
      >
        <Info size={14} strokeWidth={2} aria-hidden="true" />
      </button>
      {info && (
        <div role="note" style={{ top: info.top, left: info.left }} className="fixed z-[70] w-56 rounded-[10px] border-[0.5px] border-sepstrong bg-card p-2 text-left text-xs shadow-lg">
          <p className="mb-1 font-semibold text-label">Herkunft (gespeicherter Stand)</p>
          {herkunft.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-4 text-label2">
              {herkunft.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          ) : (
            <p className="text-label2">Dieses Recht wird nicht gewährt.</p>
          )}
        </div>
      )}
    </div>
  );
}

export function RechteTab({
  detail,
  registry,
  accountTypen,
  darfRechteVerwalten,
  onGespeichert,
}: {
  detail: PositionDetail;
  registry: RechteRegistry;
  accountTypen: AccountTyp[];
  darfRechteVerwalten: boolean;
  onGespeichert: () => void;
}) {
  const queryClient = useQueryClient();
  const gespeichert = useMemo(() => zustaendeAusOverrides(detail.overrides), [detail.overrides]);
  const [zustaende, setZustaende] = useState(gespeichert);
  const [ansicht, setAnsicht] = useState<"matrix" | "diff">("matrix");
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState(false);

  useEffect(() => setZustaende(gespeichert), [gespeichert]);

  const spalten = useMemo(() => aktionsSpalten(registry), [registry]);
  const vorlagen = useMemo(() => vorlagenScopes(detail), [detail]);
  const effektiv = useMemo(
    () => new Map(detail.effektive_rechte.map((e) => [schluessel(e.bereich, e.aktion), e])),
    [detail.effektive_rechte],
  );
  const typName = detail.account_typ?.name;
  const dirty = !zustaendeGleich(zustaende, gespeichert);
  const schreibgeschuetzt = !darfRechteVerwalten || !!detail.archiviert_am;

  const aufloeser = {
    accountTyp: (id: string) => accountTypen.find((t) => t.id === id)?.name ?? (id === detail.account_typ?.id ? typName : undefined),
    position: () => undefined,
  };

  const speichern = useMutation({
    mutationFn: () => organigrammApi.setPositionRechte(detail.id, overridesAusZustaenden(zustaende, registry)),
    onSuccess: () => {
      setFehler(null);
      setErfolg(true);
      queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
      onGespeichert();
    },
    onError: (err) => {
      setErfolg(false);
      setFehler(verstaendlicherFehler(err, "Rechte konnten nicht gespeichert werden"));
    },
  });

  function aendern(key: string, z: ZellenZustand) {
    setErfolg(false);
    setZustaende((alt) => {
      const neu = new Map(alt);
      neu.set(key, z);
      return neu;
    });
  }

  return (
    <div role="tabpanel" id="org-tabpanel-rechte" aria-labelledby="org-tab-rechte" className="space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-label2">
          Vorlage:{" "}
          <span className="font-medium text-label">{typName ?? "kein Account-Typ"}</span>
          {!typName && " – ohne Account-Typ gewährt die Position nur die Overrides unten."}
        </p>
        <SegmentedControl
          ariaLabel="Darstellung der Rechte"
          optionen={[
            { wert: "matrix", label: "Matrix" },
            { wert: "diff", label: `Abweichungen (${detail.diff_zur_vorlage.length})` },
          ]}
          wert={ansicht}
          onChange={setAnsicht}
        />
      </div>

      {!darfRechteVerwalten && (
        <p className="rounded-[10px] bg-fill px-3 py-2 text-sm text-label2">Nur Ansicht – Rechte ändern erfordert „Rechte verwalten“ im Organigramm.</p>
      )}

      {ansicht === "matrix" ? (
        <div className="overflow-x-auto rounded-[12px] bg-cell">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Rechte der Position je Bereich und Aktion</caption>
            <thead className="text-xs text-label2">
              <tr>
                <th scope="col" className="px-3 py-2">
                  Bereich
                </th>
                {spalten.map((a) => (
                  <th key={a} scope="col" className="px-1.5 py-2 font-medium">
                    {aktionLabel(a)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-sep">
              {registry.bereiche.map((b) => (
                <tr key={b.key}>
                  <th scope="row" className="px-3 py-2 text-left font-medium text-label">
                    {b.label}
                  </th>
                  {spalten.map((a) => {
                    const key = schluessel(b.key, a);
                    if (!bereichKennt(registry, b.key, a)) {
                      return (
                        <td key={a} className="px-1.5 py-1.5 text-label3" aria-label="Nicht verfügbar">
                          –
                        </td>
                      );
                    }
                    const eff = effektiv.get(key);
                    return (
                      <td key={a} className="px-1.5 py-1.5">
                        <Zelle
                          bereich={b.key}
                          bereichLabel={b.label}
                          aktion={a}
                          registry={registry}
                          zustand={zustaende.get(key) ?? { modus: "vorlage" }}
                          vorlage={vorlagen.get(key) ?? null}
                          herkunft={eff ? herkunftTexte(eff.herkunft, aufloeser) : []}
                          schreibgeschuetzt={schreibgeschuetzt}
                          onAendern={(z) => aendern(key, z)}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : detail.diff_zur_vorlage.length === 0 ? (
        <p className="rounded-[12px] bg-cell px-3 py-3 text-sm text-label2">Keine Abweichungen – die Position nutzt die Vorlage unverändert.</p>
      ) : (
        <div className="overflow-x-auto rounded-[12px] bg-cell">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Abweichungen der Position von der Vorlage</caption>
            <thead className="text-xs text-label2">
              <tr>
                <th scope="col" className="px-3 py-2">Recht</th>
                <th scope="col" className="px-3 py-2">Abweichung</th>
                <th scope="col" className="px-3 py-2">Vorlage</th>
                <th scope="col" className="px-3 py-2">Position</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep">
              {detail.diff_zur_vorlage.map((d) => (
                <tr key={schluessel(d.bereich, d.aktion)}>
                  <td className="px-3 py-2 text-label">
                    {registry.bereiche.find((b) => b.key === d.bereich)?.label ?? d.bereich} – {aktionLabel(d.aktion)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        d.art === "entfernt" ? "bg-st-fehlt-bg text-st-fehlt" : d.art === "hinzugefuegt" ? "bg-st-erledigt-bg text-st-erledigt" : "bg-st-arbeit-bg text-st-arbeit"
                      }`}
                    >
                      {DIFF_LABEL[d.art]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-label2">{d.typ_scope ? scopeLabel(d.typ_scope) : "nicht erlaubt"}</td>
                  <td className="px-3 py-2 text-label2">{d.position_scope ? scopeLabel(d.position_scope) : "nicht erlaubt"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {fehler && (
        <p role="alert" className="text-sm text-st-fehlt">
          {fehler}
        </p>
      )}
      {!schreibgeschuetzt && (
        <div className="flex items-center gap-3">
          <button type="button" disabled={!dirty || speichern.isPending} onClick={() => speichern.mutate()} className="btn-ap-primary">
            Rechte speichern
          </button>
          <button type="button" disabled={!dirty} onClick={() => setZustaende(gespeichert)} className="btn-ap">
            Zurücksetzen
          </button>
          {erfolg && !dirty && (
            <span role="status" className="text-sm text-st-erledigt">
              Gespeichert
            </span>
          )}
        </div>
      )}
    </div>
  );
}
