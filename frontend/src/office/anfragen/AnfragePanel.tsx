import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useBestaetigung } from "../../components/ConfirmDialog";
import { Select } from "../../components/apple/Select";
import { StatusPille } from "../../components/apple/StatusPille";
import { KontaktListeKompakt } from "../../components/vorOrt/KontaktListeKompakt";
import { useAuth } from "../../context/AuthContext";
import {
  ABRECHNUNGSARTEN,
  LEISTUNGSTYP_LABEL,
  PRIORITAETEN,
  datumUhrzeit,
  nurDatum,
  useAnfrageAktionen,
} from "../../pages/feld/anfragen/anfragenGemeinsam";
import type { VorgangAbrechnungsart, VorgangAnfrage } from "../../types";
import { ANFRAGE_STATUS_PILLE } from "./statusPille";

const LINK = "text-tint-text hover:underline";

function Zeile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5 text-fliess">
      <dt className="w-28 shrink-0 text-label2">{label}</dt>
      <dd className="min-w-0 text-label">{children}</dd>
    </div>
  );
}

/** Detailpanel einer Vorgangsanfrage (Office). Mit `key={anfrage.id}` rendern, damit Eingaben beim Wechsel zurückgesetzt werden. */
export function AnfragePanel({ anfrage, alle }: { anfrage: VorgangAnfrage; alle: VorgangAnfrage[] }) {
  const { hatRecht } = useAuth();
  const { search } = useLocation();
  const bestaetigen = useBestaetigung();
  const { annehmen, ablehnen, fehler, laeuft } = useAnfrageAktionen(anfrage);
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [prioritaet, setPrioritaet] = useState(3);
  const [ablehnenOffen, setAblehnenOffen] = useState(false);
  const [grund, setGrund] = useState("");

  const kundenLink = hatRecht("kunden", "sehen");
  const kannBearbeiten = hatRecht("vorgaenge", "bearbeiten");
  const status = ANFRAGE_STATUS_PILLE[anfrage.status];
  const weitere = alle.filter((a) => a.kunde_id === anfrage.kunde_id && a.id !== anfrage.id).slice(0, 5);
  const kundeName = anfrage.kunde_name ?? "Kunde";

  const ablehnenBestaetigt = async () => {
    const ok = await bestaetigen({
      titel: "Anfrage ablehnen?",
      text: "Der Kunde sieht die Anfrage danach als abgelehnt.",
      bestaetigenLabel: "Ablehnen",
    });
    if (ok) ablehnen.mutate(grund.trim());
  };

  return (
    <div className="space-y-4 pt-3">
      <div>
        <p className="text-sekundaer text-label2">
          {kundenLink ? (
            <Link to={`/kunden/${anfrage.kunde_id}`} className={LINK}>
              {kundeName}
            </Link>
          ) : (
            kundeName
          )}
        </p>
        <h2 className="ap-heading mt-0.5 text-titel-mobil font-semibold text-label">{anfrage.titel}</h2>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sekundaer text-label2">
          <StatusPille status={status.ton} label={status.label} />
          eingegangen {datumUhrzeit(anfrage.created_at)} · über das Kundenportal
        </p>
      </div>

      {anfrage.beschreibung && <p className="whitespace-pre-wrap text-fliess text-label">{anfrage.beschreibung}</p>}

      <section aria-label="Angaben">
        <h3 className="text-sekundaer font-semibold text-label2">Angaben</h3>
        <dl className="mt-1">
          <Zeile label="Art">{LEISTUNGSTYP_LABEL[anfrage.leistungstyp]}</Zeile>
          <Zeile label="Standort">
            {anfrage.standort_id ? (
              <Link to={`/standorte/${anfrage.standort_id}`} className={LINK}>
                {anfrage.standort_bezeichnung ?? "Standort"}
              </Link>
            ) : (
              "–"
            )}
          </Zeile>
          <Zeile label="Anlage">
            {anfrage.anlage_id ? (
              <Link to={`/anlagen/${anfrage.anlage_id}`} className={LINK}>
                {anfrage.anlage_bezeichnung ?? "Anlage"}
              </Link>
            ) : (
              "–"
            )}
          </Zeile>
          <Zeile label="Einheit">{anfrage.einheit || "–"}</Zeile>
          <Zeile label="Zeichen">{anfrage.kunden_referenz || "–"}</Zeile>
          <Zeile label="Gestellt von">
            {anfrage.gestellt_von_name ?? "–"}
            {anfrage.gestellt_von_email && ` · ${anfrage.gestellt_von_email}`}
          </Zeile>
        </dl>
      </section>

      <KontaktListeKompakt
        titel="Ansprechpartner vor Ort"
        variante="inline"
        kontakte={(anfrage.vor_ort_kontakte ?? []).map((k) => ({ ...k, name: k.name ?? null, einheit: null, telefon: k.telefon ?? null, erreichbarkeit: k.erreichbarkeit ?? null, hinweis: k.hinweis ?? null }))}
      />

      {anfrage.status === "offen" && kannBearbeiten && (
        <section aria-label="Annehmen" className="space-y-3 rounded-[var(--radius-ap-card)] bg-fill p-3">
          <h3 className="text-sekundaer font-semibold text-label2">Annehmen</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="anfrage-abrechnungsart" className="mb-1 block text-sekundaer font-medium text-label2">
                Abrechnungsart
              </label>
              <Select id="anfrage-abrechnungsart" value={abrechnungsart} onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}>
                {ABRECHNUNGSARTEN.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="anfrage-prioritaet" className="mb-1 block text-sekundaer font-medium text-label2">
                Priorität
              </label>
              <Select id="anfrage-prioritaet" value={prioritaet} onChange={(e) => setPrioritaet(Number(e.target.value))}>
                {PRIORITAETEN.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <p className="text-sekundaer text-label2">Legt einen Vorgang mit Status „Neu“ an. Der Kunde sieht ihn danach im Portal.</p>
          {fehler && (
            <p role="alert" className="text-fliess text-st-fehlt">
              {fehler}
            </p>
          )}
          {ablehnenOffen && (
            <div className="space-y-2">
              <label htmlFor="anfrage-grund" className="block text-sekundaer font-medium text-label2">
                Grund (optional, interne Notiz)
              </label>
              <textarea
                id="anfrage-grund"
                value={grund}
                onChange={(e) => setGrund(e.target.value)}
                rows={2}
                className="w-full rounded-[var(--radius-ap-input)] border border-sep bg-transparent p-2 text-zeile text-label"
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => annehmen.mutate({ abrechnungsart, prioritaet })}
              disabled={laeuft}
              className="btn-ap-primary px-3 py-1.5 text-sekundaer font-semibold disabled:opacity-50"
            >
              Vorgang anlegen
            </button>
            {ablehnenOffen ? (
              <>
                <button type="button" onClick={() => void ablehnenBestaetigt()} disabled={laeuft} className="btn-ap px-3 py-1.5 text-sekundaer text-st-fehlt disabled:opacity-50">
                  Ablehnen
                </button>
                <button type="button" onClick={() => setAblehnenOffen(false)} className="btn-ap px-3 py-1.5 text-sekundaer">
                  Abbrechen
                </button>
              </>
            ) : (
              <button type="button" onClick={() => setAblehnenOffen(true)} disabled={laeuft} className="btn-ap px-3 py-1.5 text-sekundaer disabled:opacity-50">
                Ablehnen…
              </button>
            )}
          </div>
        </section>
      )}

      {anfrage.status === "angenommen" && (
        <section aria-label="Bearbeitung" className="space-y-1 text-fliess text-label">
          <p>
            Angenommen
            {anfrage.bearbeitet_von_name && ` von ${anfrage.bearbeitet_von_name}`}
            {anfrage.bearbeitet_am && ` am ${nurDatum(anfrage.bearbeitet_am)}`}
          </p>
          {anfrage.vorgang_id && (
            <Link to={`/vorgaenge/${anfrage.vorgang_id}`} className={`inline-block font-medium ${LINK}`}>
              Zum Vorgang {anfrage.vorgang_nummer ?? ""}
            </Link>
          )}
        </section>
      )}

      {anfrage.status === "abgelehnt" && (
        <section aria-label="Bearbeitung" className="space-y-1 text-fliess text-label">
          <p>
            Abgelehnt
            {anfrage.bearbeitet_von_name && ` von ${anfrage.bearbeitet_von_name}`}
            {anfrage.bearbeitet_am && ` am ${nurDatum(anfrage.bearbeitet_am)}`}
          </p>
          {anfrage.ablehnungsgrund && <p className="text-label2">Grund: {anfrage.ablehnungsgrund}</p>}
        </section>
      )}

      {weitere.length > 0 && (
        <section aria-label="Weitere Anfragen dieses Kunden">
          <h3 className="text-sekundaer font-semibold text-label2">Weitere Anfragen dieses Kunden</h3>
          <ul className="mt-1 divide-y divide-sep">
            {weitere.map((a) => {
              const s = ANFRAGE_STATUS_PILLE[a.status];
              return (
                <li key={a.id} className="flex items-center gap-2 py-1.5 text-fliess">
                  <StatusPille status={s.ton} label={s.label} />
                  <Link to={{ pathname: `/anfragen/${a.id}`, search }} className={`min-w-0 flex-1 truncate ${LINK}`}>
                    {a.titel}
                  </Link>
                  <span className="shrink-0 text-sekundaer text-label2">
                    {a.status === "angenommen" && a.vorgang_nummer ? a.vorgang_nummer : nurDatum(a.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
