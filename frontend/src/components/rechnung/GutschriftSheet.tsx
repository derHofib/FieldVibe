import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { Rechnung } from "../../types";
import { formatEuro } from "../../utils/format";
import {
  GUTSCHRIFT_GRUND_MAX,
  gutschriftGrundFehler,
  gutschriftMengeFehler,
  gutschriftPayload,
  gutschriftSumme,
  istAbzugsposition,
  maxGutschriftMenge,
  restMenge,
  type GutschriftAuswahl,
} from "../../utils/rechnungsart";
import { SegmentedControl } from "../apple/SegmentedControl";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung, Hinweiskasten } from "../Hinweiskasten";

const FORM_ID = "gutschrift-formular";

type Modus = "alle" | "positionen";

const MODUS_OPTIONEN: { wert: Modus; label: string }[] = [
  { wert: "alle", label: "Komplett" },
  { wert: "positionen", label: "Positionen auswählen" },
];

function mengeText(menge: number): string {
  return String(menge).replace(".", ",");
}

/** Gutschrift zu einer versendeten Rechnung. Der Server legt sie sofort als
 * versendet an (GoBD: kein Entwurf), deshalb der deutliche Hinweis im Sheet. */
export function GutschriftSheet({
  rechnung,
  onClose,
  onErstellt,
}: {
  rechnung: Rechnung;
  onClose: () => void;
  onErstellt: (gutschrift: Rechnung) => void;
}) {
  const queryClient = useQueryClient();
  // Einfache Belege ohne Positionen kennt der Server nur als "alle".
  const ohnePositionen = rechnung.positionen.length === 0;
  const [modus, setModus] = useState<Modus>("alle");
  const [auswahl, setAuswahl] = useState<GutschriftAuswahl>({});
  const [grund, setGrund] = useState("");
  const [grundBeruehrt, setGrundBeruehrt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const waehlbar = rechnung.positionen.filter((p) => !istAbzugsposition(p));

  const summe = useMemo(() => {
    if (ohnePositionen) {
      const brutto = Number(rechnung.betrag_brutto);
      return {
        netto: `-${rechnung.betrag_netto}`,
        steuer: `-${(brutto - Number(rechnung.betrag_netto)).toFixed(2)}`,
        brutto: `-${rechnung.betrag_brutto}`,
      };
    }
    const posten =
      modus === "alle"
        ? rechnung.positionen
            .map((p) => ({ position: p, menge: String(restMenge(p)) }))
            .filter((x) => Number(x.menge) > 0)
        : waehlbar
            .filter((p) => p.id in auswahl)
            .map((p) => ({ position: p, menge: auswahl[p.id].replace(",", ".") }))
            .filter((x) => Number(x.menge) > 0);
    return gutschriftSumme(posten, rechnung.mwst_satz);
  }, [ohnePositionen, modus, auswahl, rechnung, waehlbar]);

  const mengenFehler = (positionId: string): string | null => {
    const p = rechnung.positionen.find((x) => x.id === positionId);
    return p ? gutschriftMengeFehler(p, auswahl[positionId] ?? "") : null;
  };
  const gewaehlteIds = Object.keys(auswahl);
  const auswahlOk = gewaehlteIds.length > 0 && gewaehlteIds.every((id) => !mengenFehler(id));
  const grundFehler = gutschriftGrundFehler(grund);
  const hatBetrag = Number(summe.brutto) < 0;
  const gueltig = !grundFehler && (modus === "alle" ? hatBetrag : auswahlOk);

  const erstellen = useMutation({
    mutationFn: () => rechnungenApi.gutschrift(rechnung.id, gutschriftPayload(modus, auswahl, grund)),
    onSuccess: (gutschrift) => {
      queryClient.invalidateQueries({ queryKey: ["rechnung", rechnung.id] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen-uebersicht"] });
      onErstellt(gutschrift);
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  function absenden(e: FormEvent) {
    e.preventDefault();
    setGrundBeruehrt(true);
    if (!gueltig || erstellen.isPending) return;
    setFehler(null);
    erstellen.mutate();
  }

  function umschalten(id: string, an: boolean, max: number) {
    setAuswahl((alt) => {
      const neu = { ...alt };
      if (an) neu[id] = mengeText(max);
      else delete neu[id];
      return neu;
    });
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Gutschrift erstellen"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={!gueltig || erstellen.isPending}
          className="text-[17px] font-semibold text-tint-text disabled:opacity-40"
        >
          Erstellen
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} className="space-y-4 p-4">
        {fehler && <FehlerMeldung meldung={fehler} alsKasten />}

        <Hinweiskasten ton="warnung">
          <p>Die Gutschrift wird sofort versendet und festgeschrieben – sie kann danach nicht mehr geändert werden.</p>
        </Hinweiskasten>

        {ohnePositionen ? (
          <p className="text-sm text-label2">
            Diese Rechnung hat keine einzelnen Positionen – die Gutschrift gilt für den gesamten Betrag.
          </p>
        ) : (
          <SegmentedControl
            ariaLabel="Umfang der Gutschrift"
            optionen={MODUS_OPTIONEN}
            wert={modus}
            onChange={setModus}
            groesse="mobil"
            volleBreite
          />
        )}

        {modus === "alle" && !ohnePositionen && (
          <p className="text-sm text-label2">
            Alle noch nicht gutgeschriebenen Mengen werden zurückgenommen.
          </p>
        )}

        {modus === "positionen" && (
          <ul className="space-y-2" aria-label="Positionen">
            {waehlbar.map((p) => {
              const max = maxGutschriftMenge(p);
              const aktiv = p.id in auswahl;
              const fehlerText = aktiv ? mengenFehler(p.id) : null;
              return (
                <li
                  key={p.id}
                  className={`rounded-[var(--radius-ap-md)] bg-fill p-3 text-sm ${max <= 0 ? "opacity-50" : ""}`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id={`gs-pos-${p.id}`}
                      checked={aktiv}
                      disabled={max <= 0}
                      onChange={(e) => umschalten(p.id, e.target.checked, max)}
                      aria-label={`Position ${p.position} auswählen: ${p.beschreibung}`}
                      className="mt-1 h-5 w-5 shrink-0 accent-[var(--tint-solid)]"
                    />
                    <div className="min-w-0 flex-1">
                      <label htmlFor={`gs-pos-${p.id}`} className="block text-label">
                        {p.beschreibung}
                      </label>
                      <p className="text-xs text-label2">
                        {p.menge} {p.einheit} × {p.einzelpreis} EUR
                        {max <= 0
                          ? " · bereits vollständig gutgeschrieben"
                          : Number(p.bereits_gutgeschrieben ?? "0") > 0
                            ? ` · bereits gutgeschrieben: ${p.bereits_gutgeschrieben} ${p.einheit}`
                            : ""}
                      </p>
                      {aktiv && (
                        <div className="mt-2 flex items-center gap-2">
                          <label htmlFor={`gs-menge-${p.id}`} className="text-xs text-label2">
                            Menge (max. {mengeText(max)})
                          </label>
                          <input
                            id={`gs-menge-${p.id}`}
                            type="text"
                            inputMode="decimal"
                            value={auswahl[p.id]}
                            onChange={(e) => setAuswahl((alt) => ({ ...alt, [p.id]: e.target.value }))}
                            aria-invalid={!!fehlerText}
                            className="w-24 rounded-[var(--radius-ap-input)] border border-sep bg-card px-2.5 py-1.5 text-right text-sm tabular-nums text-label"
                          />
                          <span className="text-xs text-label2">{p.einheit}</span>
                        </div>
                      )}
                      {fehlerText && (
                        <p role="alert" className="mt-1 text-xs text-st-fehlt">
                          {fehlerText}
                        </p>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
            {waehlbar.length === 0 && <li className="text-sm text-label2">Keine gutschreibbaren Positionen.</li>}
          </ul>
        )}

        <div>
          <label htmlFor="gutschrift-grund" className="mb-1 block text-xs font-medium text-label2">
            Grund
          </label>
          <textarea
            id="gutschrift-grund"
            value={grund}
            onChange={(e) => setGrund(e.target.value)}
            onBlur={() => setGrundBeruehrt(true)}
            rows={3}
            aria-invalid={grundBeruehrt && !!grundFehler}
            aria-describedby="gutschrift-grund-hinweis"
            className="field-ap"
          />
          <div id="gutschrift-grund-hinweis" className="mt-1 flex justify-between text-xs">
            <span role={grundBeruehrt && grundFehler ? "alert" : undefined} className="text-st-fehlt">
              {grundBeruehrt && grundFehler ? grundFehler : ""}
            </span>
            <span className="tabular-nums text-label2">
              {grund.trim().length}/{GUTSCHRIFT_GRUND_MAX}
            </span>
          </div>
        </div>

        <div className="card-ap space-y-1 p-3 text-sm" aria-label="Summe der Gutschrift">
          <div className="flex justify-between text-label2">
            <span>Netto</span>
            <span className="tabular-nums">{formatEuro(summe.netto)}</span>
          </div>
          <div className="flex justify-between text-label2">
            <span>Steuer</span>
            <span className="tabular-nums">{formatEuro(summe.steuer)}</span>
          </div>
          <div className="flex justify-between font-semibold text-label">
            <span>Gutschrift brutto</span>
            <span className="tabular-nums">{formatEuro(summe.brutto)}</span>
          </div>
        </div>
      </form>
    </Sheet>
  );
}
