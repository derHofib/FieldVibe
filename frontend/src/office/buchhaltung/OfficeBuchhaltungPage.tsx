import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Receipt, TrendingUp, Wallet } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { auswertungApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import type { OffenerPostenEintrag } from "../../types";
import { KennzahlKarte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";

function euro(betrag: string): string {
  const zahl = Number(betrag);
  if (Number.isNaN(zahl)) return betrag;
  return zahl.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

/** Buchhaltung bricht bewusst mit der reinen Kartenform: Betraege und
 * Faelligkeiten vergleicht man in Spalten deutlich schneller als in Karten.
 * Die Kennzahlen oben bleiben Karten, damit der schnelle Ueberblick zum Rest
 * der Anwendung passt. */
export function OfficeBuchhaltungPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const eingeschraenkt = currentUser?.nur_zugewiesene_kunden === true;
  const { data, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["auswertung", "offene-posten"],
    queryFn: () => auswertungApi.offenePosten(),
    enabled: !eingeschraenkt,
  });

  const ueberfaellig = (data?.debitoren ?? []).filter((d) => d.tage_ueberfaellig > 0);
  const summeUeberfaellig = ueberfaellig.reduce((s, d) => s + Number(d.offener_betrag || 0), 0);

  // Vier gleich grosse Nullen in kraeftiger Schrift lesen sich wie Warnsignale;
  // gedaempft (label2 statt label3: Text braucht 4.5:1) bleibt der Blick frei.
  const alleNull =
    !!data &&
    Number(data.summe_debitoren) === 0 &&
    Number(data.summe_kreditoren) === 0 &&
    summeUeberfaellig === 0 &&
    data.debitoren.length === 0 &&
    data.kreditoren.length === 0;
  const wertKlasse = alleNull ? "text-label2" : undefined;

  if (eingeschraenkt) {
    return (
      <div>
        <SeitenKopf titel="Buchhaltung" />
        <EmptyState
          icon={Receipt}
          text="Auswertungen sind für Nutzer mit Kundeneinschränkung nicht verfügbar."
        />
      </div>
    );
  }

  return (
    <div>
      <SeitenKopf titel="Buchhaltung" />

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !data ? (
        <FehlerZustand fehler={ladeFehler} was="Die Auswertung" onErneut={() => void neuLaden()} />
      ) : !data ? (
        <EmptyState icon={Receipt} text="Keine Auswertung verfügbar." />
      ) : (
        <>
          <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KennzahlKarte
              icon={Receipt}
              label="Offene Forderungen"
              wert={euro(data.summe_debitoren)}
              wertKlasse={wertKlasse}
              zusatz={`${data.debitoren.length} ${data.debitoren.length === 1 ? "Rechnung" : "Rechnungen"}`}
            />
            <KennzahlKarte
              icon={AlertCircle}
              label="Überfällig"
              wert={euro(String(summeUeberfaellig))}
              wertKlasse={wertKlasse}
              zusatz={
                ueberfaellig.length > 0
                  ? `${ueberfaellig.length} ${ueberfaellig.length === 1 ? "Rechnung" : "Rechnungen"} mahnfällig`
                  : alleNull
                    ? undefined
                    : "nichts überfällig"
              }
              ton={ueberfaellig.length > 0 ? "warnung" : alleNull ? "neutral" : "gut"}
            />
            <KennzahlKarte
              icon={Wallet}
              label="Offene Verbindlichkeiten"
              wert={euro(data.summe_kreditoren)}
              wertKlasse={wertKlasse}
              zusatz={`${data.kreditoren.length} ${data.kreditoren.length === 1 ? "Eingangsrechnung" : "Eingangsrechnungen"}`}
            />
            <KennzahlKarte
              icon={TrendingUp}
              label="Saldo"
              wert={euro(String(Number(data.summe_debitoren) - Number(data.summe_kreditoren)))}
              wertKlasse={wertKlasse}
              zusatz="Forderungen minus Verbindlichkeiten"
            />
          </div>
          {alleNull && (
            <p className="-mt-2 mb-5 flex items-center gap-1.5 text-sekundaer text-st-erledigt">
              <CheckCircle2 size={14} strokeWidth={2} aria-hidden="true" />
              Nichts überfällig
            </p>
          )}

          <PostenTabelle
            titel="Offene Posten – Debitoren"
            eintraege={data.debitoren}
            onOeffnen={(id) => navigate(`/rechnungen/${id}`)}
          />

          <div className="mt-5">
            <PostenTabelle
              titel="Offene Posten – Kreditoren"
              eintraege={data.kreditoren}
              onOeffnen={(id) => navigate(`/rechnungseingang/${id}`)}
            />
          </div>
        </>
      )}
    </div>
  );
}

function PostenTabelle({
  titel,
  eintraege,
  onOeffnen,
}: {
  titel: string;
  eintraege: OffenerPostenEintrag[];
  onOeffnen: (id: string) => void;
}) {
  return (
    <div>
      <h2 className="mb-2 text-fliess font-bold text-label">{titel}</h2>
      {eintraege.length === 0 ? (
        <EmptyState icon={Wallet} text="Nichts offen." />
      ) : (
        <TabellenRahmen>
          <table className="w-full border-collapse text-sekundaer">
            <thead>
              <tr className="bg-fill">
                <Th>Nummer</Th>
                <Th>Partner</Th>
                <Th rechts>Offener Betrag</Th>
                <Th>Fällig am</Th>
                <Th rechts>Überfällig</Th>
              </tr>
            </thead>
            <tbody>
              {eintraege.map((e) => (
                <tr
                  key={e.id}
                  onClick={() => onOeffnen(e.id)}
                  className="cursor-pointer border-b border-sep last:border-b-0 hover:bg-fill"
                >
                  <td className="px-3.5 py-2.5 font-semibold text-label">
                    {e.nummer}
                  </td>
                  <td className="px-3.5 py-2.5 text-label">
                    {e.partner_name}
                  </td>
                  <td className="px-3.5 py-2.5 text-right font-bold tabular-nums text-label">
                    {euro(e.offener_betrag)}
                  </td>
                  <td className="px-3.5 py-2.5 tabular-nums text-label2">
                    {e.faellig_am ?? "–"}
                  </td>
                  <td className="px-3.5 py-2.5 text-right">
                    {e.tage_ueberfaellig > 0 ? (
                      <span className="rounded-full bg-st-fehlt-bg px-2 py-0.5 text-meta font-semibold text-st-fehlt ">
                        {e.tage_ueberfaellig} Tage
                      </span>
                    ) : (
                      <span className="text-label2">–</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabellenRahmen>
      )}
    </div>
  );
}

function Th({ children, rechts = false }: { children: React.ReactNode; rechts?: boolean }) {
  return (
    <th
      className={`border-b border-sep px-3.5 py-2 text-meta font-bold tracking-wide text-label2 uppercase 0 ${
        rechts ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}
