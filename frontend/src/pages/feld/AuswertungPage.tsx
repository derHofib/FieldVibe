import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Receipt } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { auswertungApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerMeldung, Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../api/client";
import { downloadBlob } from "../../utils/download";
import { datumZuIso, heuteIso } from "../../utils/format";
import { istModulAktiv } from "../../utils/module";
import { istErloeskontoFehler } from "../../utils/steuer";

function ersterTagDesMonats(): string {
  const heute = new Date();
  return datumZuIso(new Date(heute.getFullYear(), heute.getMonth(), 1));
}

export function AuswertungPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");
  const eingeschraenkt = currentUser?.nur_zugewiesene_kunden === true;

  const [von, setVon] = useState(ersterTagDesMonats());
  const [bis, setBis] = useState(heuteIso());

  const { data: bericht, isFetching, refetch } = useQuery({
    queryKey: ["ust-va", von, bis],
    queryFn: () => auswertungApi.ustVa(von, bis),
    enabled: false,
  });

  const { data: offenePosten } = useQuery({
    queryKey: ["offene-posten"],
    queryFn: auswertungApi.offenePosten,
    enabled: abrechnungAktiv && kannSehen && !eingeschraenkt,
  });

  const datevMutation = useMutation({
    mutationFn: () => auswertungApi.datevExportCsv(von, bis),
    onSuccess: (blob) => downloadBlob(blob, `DATEV-Export_${von}_${bis}.csv`),
  });

  const datevMeldung = datevMutation.error instanceof ApiError ? datevMutation.error.message : null;

  if (!abrechnungAktiv || !kannSehen) return <Navigate to="/feed" replace />;

  if (eingeschraenkt) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Receipt}
          text="Auswertungen sind für Nutzer mit Kundeneinschränkung nicht verfügbar."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-label">Auswertung</h1>
      </div>

      {offenePosten && (offenePosten.debitoren.length > 0 || offenePosten.kreditoren.length > 0) && (
        <div className="card-ap p-4">
          <h2 className="mb-2 text-sm font-semibold text-label2">Offene Posten</h2>

          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-md bg-st-arbeit-bg p-2 ">
              <div className="text-xs text-st-arbeit ">Debitoren (Kunden schulden)</div>
              <div className="font-semibold text-st-arbeit ">
                {offenePosten.summe_debitoren} EUR
              </div>
            </div>
            <div className="border border-sepstrong p-2">
              <div className="text-xs text-label2">Kreditoren (wir schulden)</div>
              <div className="font-semibold text-label">
                {offenePosten.summe_kreditoren} EUR
              </div>
            </div>
          </div>

          {offenePosten.debitoren.length > 0 && (
            <>
              <div className="mb-1 mt-4 flex flex-wrap gap-1.5">
                {offenePosten.debitoren_buckets.map((b) => (
                  <span
                    key={b.label}
                    className="rounded-full bg-st-arbeit-bg px-2 py-0.5 text-xs text-st-arbeit "
                  >
                    {b.label}: {b.summe} EUR ({b.anzahl})
                  </span>
                ))}
              </div>
              <div className="space-y-1">
                {offenePosten.debitoren.map((d) => (
                  <div key={d.id} className="flex items-center justify-between rounded-md bg-fill p-2 text-sm">
                    <div>
                      <div className="text-label">{d.nummer} · {d.partner_name}</div>
                      <div className="text-xs text-label2">
                        {d.faellig_am
                          ? `Fällig ${new Date(d.faellig_am).toLocaleDateString("de-DE")}${d.tage_ueberfaellig > 0 ? ` · ${d.tage_ueberfaellig} Tage überfällig` : ""}`
                          : "Kein Fälligkeitsdatum"}
                      </div>
                    </div>
                    <div className="font-medium text-label">{d.offener_betrag} EUR</div>
                  </div>
                ))}
              </div>
            </>
          )}

          {offenePosten.kreditoren.length > 0 && (
            <>
              <div className="mb-1 mt-4 flex flex-wrap gap-1.5">
                {offenePosten.kreditoren_buckets.map((b) => (
                  <span
                    key={b.label}
                    className="border border-sep px-2 py-0.5 text-xs text-label"
                  >
                    {b.label}: {b.summe} EUR ({b.anzahl})
                  </span>
                ))}
              </div>
              <div className="space-y-1">
                {offenePosten.kreditoren.map((k) => (
                  <div key={k.id} className="flex items-center justify-between rounded-md bg-fill p-2 text-sm">
                    <div>
                      <div className="text-label">{k.nummer} · {k.partner_name}</div>
                      <div className="text-xs text-label2">
                        {k.faellig_am
                          ? `Fällig ${new Date(k.faellig_am).toLocaleDateString("de-DE")}${k.tage_ueberfaellig > 0 ? ` · ${k.tage_ueberfaellig} Tage überfällig` : ""}`
                          : "Kein Fälligkeitsdatum"}
                      </div>
                    </div>
                    <div className="font-medium text-label">{k.offener_betrag} EUR</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="card-ap p-4">
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-label2">
            Von
            <input
              type="date"
              value={von}
              onChange={(e) => setVon(e.target.value)}
              className="mt-1 w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </label>
          <label className="text-xs text-label2">
            Bis
            <input
              type="date"
              value={bis}
              onChange={(e) => setBis(e.target.value)}
              className="mt-1 w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </label>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="btn-touch mt-3 w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          USt-VA-Bericht laden
        </button>
      </div>

      {bericht && (
        <div className="card-ap p-4">
          <h2 className="mb-2 text-sm font-semibold text-label2">
            Umsatzsteuer (Ausgangsrechnungen)
          </h2>
          {bericht.umsatzsteuer_saetze.length === 0 ? (
            <p className="text-sm text-label2">Keine Umsätze im Zeitraum.</p>
          ) : (
            <div className="space-y-1">
              {bericht.umsatzsteuer_saetze.map((z) => (
                <div key={z.satz} className="flex justify-between text-sm">
                  <span className="text-label">
                    {z.satz}% auf {z.netto} EUR
                  </span>
                  <span className="font-medium text-label">{z.steuer} EUR</span>
                </div>
              ))}
            </div>
          )}

          {(bericht.sonstige_umsaetze ?? []).length > 0 && (
            <>
              <h2 className="mb-2 mt-4 text-sm font-semibold text-label2">Weitere Umsätze (ohne Umsatzsteuer)</h2>
              <div className="space-y-1">
                {bericht.sonstige_umsaetze!.map((u) => (
                  <div key={u.kategorie} className="flex justify-between gap-3 text-sm">
                    <span className="text-label">{u.bezeichnung}</span>
                    <span className="shrink-0 font-medium tabular-nums text-label">{u.netto} EUR</span>
                  </div>
                ))}
              </div>
              <p className="mt-1 text-xs text-label2">Die Kennzahl ordnet der Steuerberater zu.</p>
            </>
          )}

          <h2 className="mb-2 mt-4 text-sm font-semibold text-label2">
            Vorsteuer (Eingangsrechnungen)
          </h2>
          {bericht.vorsteuer_saetze.length === 0 ? (
            <p className="text-sm text-label2">Keine Vorsteuer im Zeitraum.</p>
          ) : (
            <div className="space-y-1">
              {bericht.vorsteuer_saetze.map((z) => (
                <div key={z.satz} className="flex justify-between text-sm">
                  <span className="text-label">
                    {z.satz}% auf {z.netto} EUR
                  </span>
                  <span className="font-medium text-label">{z.steuer} EUR</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 space-y-1 border-t border-sep pt-3 text-sm ">
            <div className="flex justify-between text-label2">
              <span>Summe Umsatzsteuer</span>
              <span>{bericht.summe_umsatzsteuer} EUR</span>
            </div>
            <div className="flex justify-between text-label2">
              <span>Summe Vorsteuer</span>
              <span>{bericht.summe_vorsteuer} EUR</span>
            </div>
            <div className="flex justify-between text-base font-bold text-label">
              <span>{Number(bericht.zahllast) >= 0 ? "Zahllast" : "Vorsteuerüberhang"}</span>
              <span>{bericht.zahllast} EUR</span>
            </div>
          </div>
        </div>
      )}

      <div className="card-ap p-4">
        <h2 className="mb-1 text-sm font-semibold text-label2">DATEV-Export</h2>
        <p className="mb-3 text-xs text-label2">
          Buchungsstapel-CSV auf Basis gängiger SKR03-Konten -- vor dem ersten echten Import bitte mit
          dem Steuerberater abstimmen.
        </p>
        <button
          onClick={() => datevMutation.mutate()}
          disabled={datevMutation.isPending}
          className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
        >
          <Download size={15} strokeWidth={2} /> DATEV-Export (CSV)
        </button>
        {datevMutation.isError && (
          <div className="mt-3">
            {datevMeldung && istErloeskontoFehler(datevMeldung) ? (
              <Hinweiskasten ton="warnung" titel="Erlöskonto fehlt">
                <p>{datevMeldung}</p>
                <p>
                  <Link to="/integrationen" className="font-semibold underline underline-offset-2">
                    Zu den Firmendaten
                  </Link>
                </p>
              </Hinweiskasten>
            ) : (
              <FehlerMeldung alsKasten meldung={datevMeldung ?? "DATEV-Export fehlgeschlagen"} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
