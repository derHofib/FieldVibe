import { useState } from "react";

import { Abschnitt, ABSCHNITT_AKTION } from "../vorgang/Abschnitt";
import { ApiError } from "../../../api/client";
import { Sheet } from "../../../components/apple/Sheet";
import { useBestaetigung } from "../../../components/ConfirmDialog";
import { FehlerMeldung } from "../../../components/Hinweiskasten";
import { SkeletonList } from "../../../components/Skeleton";
import {
  useVorOrtEntfernen,
  useVorOrtHauptkontakt,
  useVorOrtKontaktAendern,
  useVorOrtKontakteFuerZiel,
} from "../../../hooks/useVorOrt";
import type { VorOrtKontakt, VorOrtKontaktZugeordnet, VorOrtZiel } from "../../../types";
import { geerbtFussnote, kontaktAnzeigename, kontaktFormAus, kontaktFormZuBody } from "../../../utils/vorOrt";
import { KontaktFormular } from "./KontaktFormular";
import { KontaktHinzufuegenSheet } from "./KontaktHinzufuegenSheet";
import { KontaktZeile } from "./KontaktZeile";

/**
 * Kontakte vor Ort an Vorgang, Auftrag oder Projekt. Der Vorgang zeigt zusätzlich die vom Auftrag/Projekt geerbten
 * (nicht entfernbar). `kontakte` übergibt die schon geladene Liste (Vorgang-Detail-Antwort, offline im Cache) --
 * dann gibt es keine eigene Abfrage. `eingebettet` rendert ohne eigene Karte, z. B. innerhalb der Gruppe "Vor Ort".
 */
export function VorOrtKontakteAbschnitt({
  ziel,
  zielId,
  kundeId,
  standortId,
  darfBearbeiten,
  layout,
  kontakte,
  eingebettet = false,
}: {
  ziel: VorOrtZiel;
  zielId: string;
  kundeId: string | null;
  standortId: string | null;
  darfBearbeiten: boolean;
  layout: "feld" | "office";
  kontakte?: VorOrtKontaktZugeordnet[];
  eingebettet?: boolean;
}) {
  const bestaetigen = useBestaetigung();
  const [hinzufuegen, setHinzufuegen] = useState(false);
  const [bearbeiten, setBearbeiten] = useState<VorOrtKontakt | null>(null);
  const abfrage = useVorOrtKontakteFuerZiel(ziel, zielId, kontakte === undefined);
  const haupt = useVorOrtHauptkontakt();
  const entfernen = useVorOrtEntfernen();
  const aendern = useVorOrtKontaktAendern();

  const liste = kontakte ?? abfrage.data ?? [];
  const laedt = kontakte === undefined && abfrage.isLoading;
  const fehlgeschlagen = kontakte === undefined && abfrage.isError && !abfrage.data;
  const fussnote = geerbtFussnote(liste, ziel);
  const mutationFehler = [haupt.error, entfernen.error].find(Boolean);

  const hinzufuegenKnopf =
    darfBearbeiten &&
    (kundeId ? (
      <button type="button" onClick={() => setHinzufuegen(true)} className={ABSCHNITT_AKTION}>
        + Kontakt
      </button>
    ) : (
      <span className="text-sekundaer text-label2">Erst einen Auftraggeber setzen</span>
    ));

  const inhalt = (
    <>
      {laedt ? (
        <SkeletonList count={1} />
      ) : fehlgeschlagen ? (
        <FehlerMeldung alsKasten meldung="Kontakte vor Ort konnten nicht geladen werden." />
      ) : liste.length === 0 ? (
        <p className="text-fliess text-label2">Noch kein Kontakt vor Ort hinterlegt.</p>
      ) : (
        <ul className="divide-y-[0.5px] divide-sep">
          {liste.map((z) => (
            <KontaktZeile
              key={z.zuordnung_id}
              eintrag={z}
              ziel={ziel}
              layout={layout}
              darfBearbeiten={darfBearbeiten}
              onHauptkontakt={(h) => haupt.mutate({ zuordnungId: z.zuordnung_id, haupt: h })}
              onBearbeiten={() => setBearbeiten(z.kontakt)}
              onEntfernen={async () => {
                const name = kontaktAnzeigename(z.kontakt);
                if (
                  await bestaetigen({
                    titel: `${name} entfernen?`,
                    text: "Der Kontakt bleibt beim Kunden gespeichert und wird nur hier entfernt.",
                    bestaetigenLabel: "Entfernen",
                    destruktiv: true,
                  })
                ) {
                  entfernen.mutate(z.zuordnung_id);
                }
              }}
            />
          ))}
        </ul>
      )}
      {mutationFehler && (
        <FehlerMeldung alsKasten meldung={mutationFehler instanceof ApiError ? mutationFehler.message : "Aktion fehlgeschlagen."} />
      )}
      {fussnote && <p className="mt-2 text-meta text-label2">{fussnote}</p>}
      {eingebettet && hinzufuegenKnopf && <div className="mt-1 flex justify-end">{hinzufuegenKnopf}</div>}
    </>
  );

  return (
    <>
      {eingebettet ? (
        <section aria-label="Kontakte vor Ort">{inhalt}</section>
      ) : (
        <Abschnitt titel="Kontakte vor Ort" aktion={hinzufuegenKnopf || undefined}>
          {inhalt}
        </Abschnitt>
      )}
      {hinzufuegen && kundeId && (
        <KontaktHinzufuegenSheet
          ziel={ziel}
          zielId={zielId}
          kundeId={kundeId}
          standortId={standortId}
          schonZugeordnet={new Set(liste.map((z) => z.kontakt.id))}
          onClose={() => setHinzufuegen(false)}
        />
      )}
      {bearbeiten && (
        <Sheet
          offen
          onClose={() => setBearbeiten(null)}
          titel="Kontakt bearbeiten"
          links={
            <button type="button" onClick={() => setBearbeiten(null)} className="text-zeile text-tint-text">
              Abbrechen
            </button>
          }
        >
          <div className="p-4">
            <KontaktFormular
              start={kontaktFormAus(bearbeiten)}
              laeuft={aendern.isPending}
              fehler={aendern.error}
              submitLabel="Speichern"
              onSubmit={(w) => aendern.mutate({ id: bearbeiten.id, body: kontaktFormZuBody(w) }, { onSuccess: () => setBearbeiten(null) })}
              fussnote="Änderungen gelten für alle Aufträge und Vorgänge, denen dieser Kontakt zugeordnet ist."
            />
          </div>
        </Sheet>
      )}
    </>
  );
}
