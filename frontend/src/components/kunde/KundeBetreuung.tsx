import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Info, Star } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { kundenApi, usersApi } from "../../api/endpoints";
import type { Betreuer } from "../../types";
import {
  auswahlAusBetreuung,
  betreuerUmschalten,
  betreuungUnterzeile,
  hauptbetreuerUmschalten,
  kandidatenBilden,
  sichtverlust,
} from "../../utils/betreuung";
import { AbschnittsFusszeile, AbschnittskopfB } from "../apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../apple/GroupedList";
import { Monogramm } from "../apple/Monogramm";
import { SearchField } from "../apple/SearchField";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung } from "../Hinweiskasten";

function HauptStern({ className = "" }: { className?: string }) {
  return <Star size={16} strokeWidth={2} className={`shrink-0 fill-current text-st-arbeit-dot ${className}`} aria-hidden="true" />;
}

/** Abschnitt "Betreuung" im Kundenprofil (Feld-App und Office-Detailpanel). */
export function KundeBetreuung({
  kundeId,
  betreuung,
  kannVerwalten,
}: {
  kundeId: string;
  betreuung: Betreuer[];
  kannVerwalten: boolean;
}) {
  const [offen, setOffen] = useState(false);
  const haupt = betreuung.find((b) => b.hauptbetreuer);
  // Zeilen: eine je Betreuer plus ggf. "Betreuung ändern"
  const zeilen = betreuung.length + (kannVerwalten ? 1 : 0);

  return (
    <section aria-label="Betreuung">
      <AbschnittskopfB titel="Betreuung" />
      <GroupedList>
        {betreuung.length === 0 && (
          <GroupedListRow last={!kannVerwalten}>
            <span className="text-zeile text-label2">Noch niemand betreut diesen Kunden.</span>
          </GroupedListRow>
        )}
        {betreuung.map((b, i) => (
          <GroupedListRow key={b.user_id} last={i === zeilen - 1}>
            <span className={b.aktiv ? "" : "opacity-50"}>
              <Monogramm name={b.name} groesse={32} ringKlasse="ring-cell" />
            </span>
            <div className="min-w-0 flex-1">
              <p className={`truncate text-zeile ${b.aktiv ? "text-label" : "text-label3"}`}>{b.name}</p>
              <p className="truncate text-sekundaer text-label2">
                {betreuungUnterzeile(b)}
                {!b.aktiv && " · deaktiviert"}
              </p>
            </div>
            {b.hauptbetreuer && <HauptStern />}
          </GroupedListRow>
        ))}
        {kannVerwalten && (
          <GroupedListRow onClick={() => setOffen(true)} last>
            <span className="text-zeile text-tint-text">Betreuung ändern</span>
          </GroupedListRow>
        )}
      </GroupedList>
      {haupt && (
        <div className="mx-4 mt-2 flex items-start gap-2 rounded-[var(--radius-ap-md)] bg-tintbg px-3 py-2 text-sekundaer text-label">
          <Info size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-tint" aria-hidden="true" />
          <p>Neue Vorgänge für diesen Kunden werden automatisch {haupt.name} zugewiesen.</p>
        </div>
      )}
      {kannVerwalten && offen && <BetreuungSheet kundeId={kundeId} bisher={betreuung} onClose={() => setOffen(false)} />}
    </section>
  );
}

export function BetreuungSheet({
  kundeId,
  bisher,
  onClose,
}: {
  kundeId: string;
  bisher: Betreuer[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [auswahl, setAuswahl] = useState(() => auswahlAusBetreuung(bisher));
  const [suche, setSuche] = useState("");

  const { data: alle, isLoading, isError } = useQuery({
    queryKey: ["users", "auswahl"],
    queryFn: usersApi.auswahl,
  });
  const kandidaten = useMemo(() => kandidatenBilden(alle, bisher), [alle, bisher]);
  const sichtbar = kandidaten.filter((k) => k.name.toLowerCase().includes(suche.trim().toLowerCase()));
  const verlust = sichtverlust(bisher, auswahl);

  const speichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => kundenApi.betreuungSetzen(kundeId, { user_ids: auswahl.userIds, hauptbetreuer_id: auswahl.hauptId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      onClose();
    },
  });

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Betreuung"
      links={
        <button type="button" onClick={onClose} className="text-zeile text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="button"
          onClick={() => speichern.mutate()}
          disabled={speichern.isPending}
          className="text-zeile font-semibold text-tint-text disabled:opacity-50"
        >
          Fertig
        </button>
      }
    >
      <div className="space-y-2 p-4">
        <SearchField value={suche} onChange={setSuche} placeholder="Mitarbeiter suchen" groesse="mobil" ariaLabel="Mitarbeiter suchen" />
        {isLoading ? (
          <p className="px-4 py-3 text-sekundaer text-label2">Mitarbeiter werden geladen…</p>
        ) : isError ? (
          <FehlerMeldung alsKasten meldung="Mitarbeiterliste konnte nicht geladen werden." />
        ) : (
          <GroupedList>
            {sichtbar.length === 0 && (
              <GroupedListRow last>
                <span className="text-sekundaer text-label2">Keine Mitarbeiter gefunden.</span>
              </GroupedListRow>
            )}
            {sichtbar.map((k, i) => {
              const gewaehlt = auswahl.userIds.includes(k.id);
              const istHaupt = auswahl.hauptId === k.id;
              return (
                <div key={k.id} className="relative flex items-center pr-2">
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={gewaehlt}
                    onClick={() => setAuswahl((a) => betreuerUmschalten(a, k.id))}
                    className="flex min-h-12 min-w-0 flex-1 items-center gap-3 py-2 pl-4 text-left"
                  >
                    <span className={k.aktiv ? "" : "opacity-50"}>
                      <Monogramm name={k.name} groesse={32} ringKlasse="ring-cell" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={`block truncate text-zeile ${k.aktiv ? "text-label" : "text-label3"}`}>{k.name}</span>
                      <span className="block truncate text-sekundaer text-label2">
                        {[k.accountTyp, k.nurBetreuteKunden ? "sieht nur betreute Kunden" : null, k.aktiv ? null : "deaktiviert"]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center" aria-hidden="true">
                      {gewaehlt && <Check size={18} strokeWidth={2.5} className="text-tint" />}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label="Als Hauptbetreuer festlegen"
                    aria-pressed={istHaupt}
                    // Deaktivierte lassen sich nicht neu wählen -- nur ein bereits gesetzter Stern darf weg.
                    disabled={!k.aktiv && !gewaehlt}
                    onClick={() => setAuswahl((a) => hauptbetreuerUmschalten(a, k.id))}
                    className="btn-touch flex h-11 w-11 shrink-0 items-center justify-center disabled:opacity-40"
                  >
                    <Star
                      size={20}
                      strokeWidth={1.75}
                      className={istHaupt ? "fill-current text-st-arbeit-dot" : "text-label3"}
                      aria-hidden="true"
                    />
                  </button>
                  {i < sichtbar.length - 1 && <span className="absolute right-0 bottom-0 left-16 h-px bg-sep" aria-hidden="true" />}
                </div>
              );
            })}
          </GroupedList>
        )}
        {verlust.map((b) => (
          <p key={b.user_id} role="alert" className="rounded-[var(--radius-ap-md)] bg-st-arbeit-bg px-3 py-2 text-sekundaer text-st-arbeit">
            {b.name} sieht nur betreute Kunden und sieht diesen Kunden und seine Vorgänge danach nicht mehr.
          </p>
        ))}
        {speichern.isError && (
          <FehlerMeldung
            alsKasten
            meldung={speichern.error instanceof ApiError ? speichern.error.message : "Speichern fehlgeschlagen"}
          />
        )}
        <AbschnittsFusszeile>
          Der Stern markiert den Hauptbetreuer. Neue Vorgänge des Kunden werden ihm automatisch zugewiesen.
        </AbschnittsFusszeile>
      </div>
    </Sheet>
  );
}
