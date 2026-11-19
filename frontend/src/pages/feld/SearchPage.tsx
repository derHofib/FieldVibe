import { useQuery } from "@tanstack/react-query";
import { SearchX } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { tagsApi } from "../../api/endpoints";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { SearchField } from "../../components/apple/SearchField";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import {
  erlaubteKategorien,
  formatAnzahl,
  KATEGORIE_INFO,
  type SucheEintrag,
  trefferZuEintrag,
  verlaufZuEintrag,
} from "../../components/suche/kategorien";
import { NachladenAnker } from "../../components/suche/NachladenAnker";
import { SuchFilterLeiste } from "../../components/suche/SuchFilterLeiste";
import { TrefferInhalt } from "../../components/suche/TrefferZeile";
import { useGlobaleSuche } from "../../components/suche/useGlobaleSuche";
import { merkeZuletzt, useZuletztGeoeffnet } from "../../components/suche/zuletztGeoeffnet";
import { useAuth } from "../../context/AuthContext";

const GRUPPENKOPF = "flex items-center justify-between px-5 pt-4 pb-1.5 text-meta font-semibold tracking-wide text-label2 uppercase";

/** Mobile Vollbild-Suche (Feld-App): dieselbe Logik wie das Office-Fenster, ohne Glas -- die Tastatur nimmt die halbe Höhe. */
export function SearchPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const suche = useGlobaleSuche();
  const { eintraege: zuletzt, leeren } = useZuletztGeoeffnet();
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const { eingabe, setEingabe, begriff, aktiv, kategorie, setKategorie } = suche;
  const hatEingabe = eingabe.trim().length > 0;

  function oeffnen(eintrag: SucheEintrag) {
    if ("tag" in eintrag.ziel) {
      setEingabe(`#${eintrag.ziel.tag}`);
      return;
    }
    if (eintrag.kategorie !== "seite" && currentUser) {
      merkeZuletzt(currentUser.id, {
        kategorie: eintrag.kategorie,
        id: eintrag.id,
        titel: eintrag.titel,
        untertitel: eintrag.untertitel,
        status: eintrag.statusRoh,
      });
    }
    navigate(eintrag.ziel.pfad);
  }

  const zeile = (e: SucheEintrag, letzte: boolean, b: string) => (
    <GroupedListRow key={e.key} onClick={() => oeffnen(e)} navigierbar={!e.status} last={letzte} minHoehe={48}>
      <TrefferInhalt eintrag={e} begriff={b} feld />
    </GroupedListRow>
  );

  const gruppen = suche.gruppen
    .map((g) => ({
      kategorie: g.kategorie,
      eintraege: g.treffer.map((t) => trefferZuEintrag(t, "feld")).filter((e): e is SucheEintrag => !!e),
    }))
    .filter((g) => g.eintraege.length > 0);
  const verlauf = zuletzt.map((e) => verlaufZuEintrag(e, "feld")).filter((e): e is SucheEintrag => !!e);
  const wartet = hatEingabe && (!aktiv || suche.laedt);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <SearchField
          autoFocus
          groesse="mobil"
          value={eingabe}
          onChange={setEingabe}
          placeholder="Kunde, Anlage, Vorgangsnummer, #Tag…"
          className="flex-1"
        />
        <button type="button" onClick={() => navigate(-1)} className="btn-touch shrink-0 text-zeile text-tint-text">
          Abbrechen
        </button>
      </div>

      <div className="-mx-3">
        <SuchFilterLeiste
          suche={suche}
          erlaubt={erlaubteKategorien(suche.anzahl, currentUser, hatRecht, "feld")}
          variante="feld"
        />
      </div>

      {!hatEingabe && (
        <>
          {verlauf.length > 0 && (
            <section>
              <div className={GRUPPENKOPF}>
                <h2>Zuletzt geöffnet</h2>
                <button type="button" onClick={leeren} className="btn-touch font-medium tracking-normal text-tint-text normal-case">
                  Verlauf leeren
                </button>
              </div>
              <GroupedList>{verlauf.map((e, i) => zeile(e, i === verlauf.length - 1, ""))}</GroupedList>
            </section>
          )}
          {tags && tags.length > 0 && (
            <section>
              <h2 className={GRUPPENKOPF}>Tags</h2>
              <div className="flex flex-wrap gap-2 px-1">
                {tags.map((tag) => (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => setEingabe(`#${tag.label}`)}
                    className="btn-touch card-ap rounded-full px-3 py-1.5 text-sekundaer text-label"
                  >
                    #{tag.label}
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {hatEingabe && (
        <div className={suche.veraltet ? "opacity-60" : undefined}>
          {gruppen.map((g) => {
            const n = suche.anzahl?.[g.kategorie];
            const plural = KATEGORIE_INFO[g.kategorie].plural;
            return (
              <section key={g.kategorie}>
                <div className={GRUPPENKOPF}>
                  <h2>{n !== undefined ? `${plural} · ${formatAnzahl(n)}` : plural}</h2>
                  {kategorie === "alle" && g.kategorie !== "tag" && (
                    <button
                      type="button"
                      onClick={() => setKategorie(g.kategorie)}
                      aria-label={`Alle in ${plural}`}
                      className="btn-touch font-medium tracking-normal text-tint-text normal-case"
                    >
                      Alle
                    </button>
                  )}
                </div>
                <GroupedList>{g.eintraege.map((e, i) => zeile(e, i === g.eintraege.length - 1, begriff))}</GroupedList>
              </section>
            );
          })}
          {suche.hatWeitere && <NachladenAnker feld onSichtbar={suche.ladeWeitere} laeuft={suche.ladeWeitereLaeuft} />}
          {wartet && gruppen.length === 0 && <SkeletonList count={3} />}
          {suche.fehler && gruppen.length === 0 && (
            <FehlerZustand fehler={suche.fehler} was="Die Suche" onErneut={suche.neuLaden} />
          )}
          {!wartet && !suche.fehler && gruppen.length === 0 && (
            <EmptyState icon={SearchX} text={`Keine Treffer für „${eingabe.trim()}“`} />
          )}
        </div>
      )}
    </div>
  );
}
