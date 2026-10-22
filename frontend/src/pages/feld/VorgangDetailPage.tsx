import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { anlagenApi, kundenApi, standorteApi, usersApi, vorgaengeApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import { cacheKunde, getCachedKunde } from "../../offline/cache";
import type { Adresse } from "../../types";
import { AbschnittsNavigation } from "./vorgangDetail/AbschnittsNavigation";
import { ArbeitszeitInhalt } from "./vorgangDetail/ArbeitszeitInhalt";
import { DichteLinkeSpalte } from "./vorgangDetail/DichteLinkeSpalte";
import { KennzahlenZeile } from "./vorgangDetail/KennzahlenZeile";
import { KopfLeiste } from "./vorgangDetail/KopfLeiste";
import { KurzUebersicht } from "./vorgangDetail/KurzUebersicht";
import { PositionenInhalt } from "./vorgangDetail/PositionenInhalt";
import { PrimaerAktionsLeiste } from "./vorgangDetail/PrimaerAktionsLeiste";
import { UnterseitenRahmen } from "./vorgangDetail/UnterseitenRahmen";
import { VerlaufInhalt } from "./vorgangDetail/VerlaufInhalt";
import { ZeitSheets } from "./vorgangDetail/ZeitSheets";
import {
  ANCHOR_ABSCHNITTE, VORGANG_STATUS_GESCHLOSSEN, VORGANG_STATUS_ZEIT_GESPERRT,
} from "./vorgangDetail/konstanten";
import { useVorgangMaengel } from "./vorgangDetail/useVorgangMaengel";
import { useVorgangPartner } from "./vorgangDetail/useVorgangPartner";
import { useVorgangPositionen } from "./vorgangDetail/useVorgangPositionen";
import { useVorgangTermine } from "./vorgangDetail/useVorgangTermine";
import { useVorgangUebersicht } from "./vorgangDetail/useVorgangUebersicht";
import { useVorgangVerlauf } from "./vorgangDetail/useVorgangVerlauf";
import { useVorgangZeit } from "./vorgangDetail/useVorgangZeit";

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function VorgangDetailPage({
  id: idProp,
  layout = "kompakt",
  // Eigene Unterseite fuer einen einzelnen Abschnitt (Routen /vorgaenge/
  // :id/zeit, /verlauf, /positionen, siehe App.tsx/OfficeApp.tsx und
  // ABSCHNITT_ROUTE in vorgangDetail/konstanten.ts) -- ausgeloest ueber die jeweilige Anker-Pille
  // bzw. den Einstiegspunkt auf der Uebersicht im "kompakt"-Layout. Im
  // "dicht"-Layout (Office-Inspektor-Spalte) ohne Wirkung, dort sind alle
  // Abschnitte ohnehin schon echte Tabs.
  ansicht = "voll",
  // Nur im "dicht"-Layout relevant: die Office-Vollbild-Route (siehe
  // OfficeApp.tsx, /vorgaenge/:id/vollbild) hat echte Desktop-Breite statt
  // der schmalen Inspektor-Spalte in VorgaengeListe.tsx -- dort lohnt sich
  // eine feste zweite Spalte fuer den Verlauf (immer sichtbar statt Tab,
  // siehe verlaufSpalteBreit), in der schmalen Spalte nicht.
  breit = false,
}: {
  id?: string;
  layout?: "kompakt" | "dicht";
  ansicht?: "voll" | "zeit" | "verlauf" | "positionen";
  breit?: boolean;
} = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Nur im "dicht"-Layout (Office-Inspektor-Spalte, siehe VorgaengeListe.tsx)
  // werden die Abschnitte zu echten Tabs (ein Panel sichtbar) statt der
  // mobilen Anker-Scroll-Liste (alle Abschnitte untereinander).
  const [desktopTab, setDesktopTab] = useState(ANCHOR_ABSCHNITTE[0].ziel);
  const istAktiverTab = (ziel: string) => layout !== "dicht" || desktopTab === ziel;
  const tabPanelProps = (ziel: string) =>
    layout === "dicht" ? { role: "tabpanel" as const, "aria-labelledby": `tab-${ziel}` } : {};
  const { hatRecht } = useAuth();
  // Gemeinsame Fehleranzeige fuer alle Aktionen der Bereichs-Hooks, die keinen eigenen
  // Inline-Fehlertext neben einem Formular haben (z. B. Uebernehmen, Foto-
  // Upload, Timer) -- sonst verpufft ein Fehlschlag beim Techniker unsichtbar.
  const [aktionsFehler, setAktionsFehler] = useState<string | null>(null);
  const meldeAktionsFehler = (err: unknown) =>
    setAktionsFehler(
      err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
    );

  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  const {
    data: vorgang,
    isError: vorgangIstFehler,
    error: vorgangFehler,
  } = useQuery({
    queryKey: ["vorgang", id],
    queryFn: () => vorgaengeApi.get(id!),
    enabled: !!id,
    retry: false,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", vorgang?.kunde_id],
    queryFn: async () => {
      try {
        const result = await kundenApi.get(vorgang!.kunde_id);
        await cacheKunde(result);
        return result;
      } catch (err) {
        if (!navigator.onLine) {
          const cached = await getCachedKunde(vorgang!.kunde_id);
          if (cached) return cached;
        }
        throw err;
      }
    },
    enabled: !!vorgang,
  });
  const { data: anlage } = useQuery({
    queryKey: ["anlage", vorgang?.anlage_id],
    queryFn: () => anlagenApi.get(vorgang!.anlage_id!),
    enabled: !!vorgang?.anlage_id,
  });
  const { data: standort } = useQuery({
    queryKey: ["standort", vorgang?.standort_id],
    queryFn: () => standorteApi.get(vorgang!.standort_id!),
    enabled: !!vorgang?.standort_id,
  });
  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl });
  const deleteVorgangMutation = useMutation({
    mutationFn: () => vorgaengeApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      navigate("/feed");
    },
    onError: meldeAktionsFehler,
  });

  const partnerDaten = useVorgangPartner({ id, meldeAktionsFehler, vorgang });
  const uebersichtDaten = useVorgangUebersicht({ id, meldeAktionsFehler, vorgang });
  const zeitDaten = useVorgangZeit({ id, meldeAktionsFehler });
  const verlaufDaten = useVorgangVerlauf({
    id,
    meldeAktionsFehler,
    partnerKommentarMoeglich: partnerDaten.partnerKommentarMoeglich,
    setAktionsFehler,
  });
  const positionenDaten = useVorgangPositionen({ id, kunde, meldeAktionsFehler, vorgang });
  const termineDaten = useVorgangTermine({ id, meldeAktionsFehler });
  const maengelDaten = useVorgangMaengel({ id, meldeAktionsFehler });

  const { uebernehmenMutation } = uebersichtDaten;
  const { laufenderTimer, stopTimerMutation, timerLaeuftHier } = zeitDaten;
  const { rechnungAusVorgangMutation } = positionenDaten;

  if (vorgangIstFehler) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Ban}
          text={
            vorgangFehler instanceof ApiError && vorgangFehler.status === 404
              ? "Vorgang nicht gefunden oder kein Zugriff."
              : "Vorgang konnte nicht geladen werden."
          }
        />
      </div>
    );
  }
  if (!vorgang) return <p className="text-center text-label2">Lädt…</p>;

  // Eigene Adresse am Vorgang hat Vorrang; ohne sie zeigen wir die Adresse
  // des zugeordneten Standorts bzw. ersatzweise der Anlage, damit die Karte
  // auch beim reinen Auswaehlen eines Standorts erscheint.
  const anzeigeAdresse: Adresse | null = vorgang.adresse ?? standort?.adresse ?? anlage?.adresse ?? null;
  // Koordinaten nur vertrauen, wenn die angezeigte Adresse tatsaechlich vom
  // Standort/der Anlage kommt (siehe Kommentar zu anzeigeAdresse) -- ein
  // manueller Adress-Override am Vorgang selbst hat keine eigenen
  // geo_lat/geo_lng-Spalten und darf nicht versehentlich die Koordinaten
  // eines ganz anderen Orts anzeigen.
  const kartenKoordinaten: { lng: number; lat: number } | null =
    !vorgang.adresse && standort?.geo_lat != null && standort?.geo_lng != null
      ? { lng: standort.geo_lng, lat: standort.geo_lat }
      : !vorgang.adresse && anlage?.geo_lat != null && anlage?.geo_lng != null
        ? { lng: anlage.geo_lng, lat: anlage.geo_lat }
        : null;

  // Eine klare Primäraktion statt vieler gleich gewichteter Text-Links --
  // je nach Zustand des Vorgangs genau EIN naheliegender naechster Schritt,
  // als Sticky-Button am unteren Bildschirmrand (siehe PrimaerAktionsLeiste).
  // Reihenfolge = Prioritaet: Zuweisung vor laufendem Timer vor
  // Abrechnung vor normaler Zeiterfassung.
  const primaerAktion: { label: string; onClick: () => void; disabled?: boolean } | null =
    !vorgang.zugewiesener_user_id && !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
      ? {
          label: "Ticket übernehmen",
          onClick: () => uebernehmenMutation.mutate(),
          disabled: uebernehmenMutation.isPending,
        }
      : timerLaeuftHier
        ? {
            label: "Zeit stoppen",
            onClick: () => stopTimerMutation.mutate(laufenderTimer!.id),
            disabled: stopTimerMutation.isPending,
          }
        : vorgang.status === "abgeschlossen" && kannDisponieren
          ? {
              label: "Rechnung erstellen",
              onClick: () => rechnungAusVorgangMutation.mutate(),
              disabled: rechnungAusVorgangMutation.isPending,
            }
          : !VORGANG_STATUS_ZEIT_GESPERRT.includes(vorgang.status)
            ? { label: "Zeit erfassen", onClick: () => navigate(`/vorgaenge/${id}/zeit`) }
            : null;

  const arbeitszeitInhalt = (
    <ArbeitszeitInhalt id={id} layout={layout} users={users} vorgang={vorgang} zeitDaten={zeitDaten} />
  );

  const verlaufInhalt = (
    <VerlaufInhalt id={id} kunde={kunde} users={users} partnerDaten={partnerDaten} verlaufDaten={verlaufDaten} />
  );

  const positionenInhalt = (
    <PositionenInhalt layout={layout} positionenDaten={positionenDaten} />
  );

  // "Vollbild"-Layout (Office-Route /vorgaenge/:id/vollbild, siehe
  // OfficeApp.tsx): Verlauf steht dort als feste zweite Spalte staendig
  // sichtbar neben den uebrigen (weiterhin per Tab umschaltbaren)
  // Abschnitten, statt selbst ein Tab zu sein -- lohnt sich nur bei
  // echter Desktop-Breite, nicht in der schmalen Inspektor-Spalte
  // (VorgaengeListe.tsx), daher eigener "breit"-Prop statt an "dicht"
  // allein gekoppelt.
  const verlaufSpalteBreit = layout === "dicht" && breit;

  const dichtLinkeSpalteInhalt = (
    <DichteLinkeSpalte
      anlage={anlage}
      anzeigeAdresse={anzeigeAdresse}
      arbeitszeitInhalt={arbeitszeitInhalt}
      istAktiverTab={istAktiverTab}
      kartenKoordinaten={kartenKoordinaten}
      kunde={kunde}
      layout={layout}
      positionenInhalt={positionenInhalt}
      standort={standort}
      tabPanelProps={tabPanelProps}
      users={users}
      vorgang={vorgang}
      maengelDaten={maengelDaten}
      partnerDaten={partnerDaten}
      termineDaten={termineDaten}
      uebersichtDaten={uebersichtDaten}
    />
  );

  const verlaufAbschnittDiv = layout === "dicht" && (
    <div
      id="abschnitt-verlauf"
      className={verlaufSpalteBreit || istAktiverTab("abschnitt-verlauf") ? "" : "hidden"}
      {...tabPanelProps("abschnitt-verlauf")}
    >
      {verlaufInhalt}
    </div>
  );

  if (ansicht === "zeit" && layout !== "dicht") {
    return (
      <UnterseitenRahmen vorgang={vorgang} kunde={kunde} id={id}>
        <div className="card-ap p-3">{arbeitszeitInhalt}</div>
        <ZeitSheets id={id} zeitDaten={zeitDaten} />
      </UnterseitenRahmen>
    );
  }

  if (ansicht === "verlauf" && layout !== "dicht") {
    return (
      <UnterseitenRahmen vorgang={vorgang} kunde={kunde} id={id}>
        <div className="card-ap p-3">{verlaufInhalt}</div>
      </UnterseitenRahmen>
    );
  }

  if (ansicht === "positionen" && layout !== "dicht") {
    return (
      <UnterseitenRahmen vorgang={vorgang} kunde={kunde} id={id}>
        <div className="card-ap p-3">{positionenInhalt}</div>
      </UnterseitenRahmen>
    );
  }

  return (
    <div className={`space-y-4 ${layout !== "dicht" && primaerAktion ? "pb-20" : ""}`}>
      <KopfLeiste
        aktionsFehler={aktionsFehler}
        anlage={anlage}
        deleteVorgangMutation={deleteVorgangMutation}
        setAktionsFehler={setAktionsFehler}
        standort={standort}
        vorgang={vorgang}
      />
      <AbschnittsNavigation
        desktopTab={desktopTab}
        id={id}
        layout={layout}
        setDesktopTab={setDesktopTab}
        verlaufSpalteBreit={verlaufSpalteBreit}
      />
      <KurzUebersicht layout={layout} vorgang={vorgang} />
      <KennzahlenZeile
        ansicht={ansicht}
        id={id}
        layout={layout}
        maengelDaten={maengelDaten}
        positionenDaten={positionenDaten}
        termineDaten={termineDaten}
        verlaufDaten={verlaufDaten}
        zeitDaten={zeitDaten}
      />

      {verlaufSpalteBreit ? (
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1 space-y-4">{dichtLinkeSpalteInhalt}</div>
          <div className="w-[380px] shrink-0">{verlaufAbschnittDiv}</div>
        </div>
      ) : (
        <>
          {dichtLinkeSpalteInhalt}
          {verlaufAbschnittDiv}
        </>
      )}

      <ZeitSheets id={id} zeitDaten={zeitDaten} />
      <PrimaerAktionsLeiste ansicht={ansicht} layout={layout} primaerAktion={primaerAktion} />
    </div>
  );
}

