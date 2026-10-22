import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { zeiterfassungApi } from "../../../api/endpoints";
import { bestaetigen } from "../../../components/apple/BestaetigungsDialog";
import { useAuth } from "../../../context/AuthContext";
import type { Zeiterfassung } from "../../../types";
import { formatSekundenAlsHHMM } from "../../../utils/duration";

/** Arbeitszeit: Timer, Zeiteinträge und der Buchungsablauf (vormerken, buchen, stornieren). */
export function useVorgangZeit({
  id,
  meldeAktionsFehler,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
}) {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const [taetigkeit, setTaetigkeit] = useState("");
  // Zeit-Tab: Sheet zum Anlegen/Bearbeiten eines Eintrags (Stufe 1, siehe
  // docs/konzepte/ZEITERFASSUNG.md) -- offen, wenn zeitSheetModus gesetzt
  // ist. "neu" oeffnet leer (vorbelegt mit diesem Vorgang, kategorie=
  // "auftrag"), km/Fahrzeug sind darin ein optionales Feld statt eines
  // eigenen "Fahrt"-Einstiegs (Konzept Abschnitt 11); ein Eintrag oeffnet
  // zum Bearbeiten.
  const [zeitSheetModus, setZeitSheetModus] = useState<"neu" | Zeiterfassung | null>(null);
  // Kleines Taetigkeits-Sheet, das automatisch nach "Stoppen" erscheint --
  // der gerade beendete Eintrag, oder null wenn keins offen ist.
  const [nachStoppenEintrag, setNachStoppenEintrag] = useState<Zeiterfassung | null>(null);
  const [nachStoppenTaetigkeit, setNachStoppenTaetigkeit] = useState("");
  // Buchungsablauf (Stufe 2, siehe docs/konzepte/ZEITERFASSUNG.md
  // Abschnitt 6.1) -- Auswahl im Zeit-Tab, alle ausgewaehlten Eintraege
  // muessen denselben Buchungsstatus haben (siehe kannZeitAuswaehlen unten).
  const [ausgewaehlteZeitIds, setAusgewaehlteZeitIds] = useState<Set<string>>(new Set());
  const [stornierenModus, setStornierenModus] = useState(false);
  const [stornierenGrund, setStornierenGrund] = useState("");
  const { data: laufenderTimer } = useQuery({
    queryKey: ["zeiterfassung-laufend"],
    queryFn: zeiterfassungApi.laufend,
  });
  const { data: zeiterfassungListe } = useQuery({
    queryKey: ["zeiterfassung", id],
    queryFn: () => zeiterfassungApi.list(id!),
    enabled: !!id,
  });
  const startTimerMutation = useMutation({
    mutationFn: () => zeiterfassungApi.start(id!, taetigkeit || undefined),
    onSuccess: () => {
      setTaetigkeit("");
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
    onError: meldeAktionsFehler,
  });

  const stopTimerMutation = useMutation({
    mutationFn: (timerId: string) => zeiterfassungApi.stop(timerId),
    onSuccess: (gestoppterEintrag) => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      // Automatisches Taetigkeits-Sheet nach dem Stoppen (Stufe 1, siehe
      // docs/konzepte/ZEITERFASSUNG.md) -- nur wenn die Taetigkeit noch
      // fehlt, sonst waere die Nachfrage ueberfluessig.
      if (!gestoppterEintrag.taetigkeit) {
        setNachStoppenEintrag(gestoppterEintrag);
        setNachStoppenTaetigkeit("");
      }
    },
    onError: meldeAktionsFehler,
  });

  const nachStoppenTaetigkeitMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.aktualisieren(nachStoppenEintrag!.id, { taetigkeit: nachStoppenTaetigkeit }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      setNachStoppenEintrag(null);
    },
    onError: meldeAktionsFehler,
  });

  function nachBuchungsaktionAufraeumen() {
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
    setAusgewaehlteZeitIds(new Set());
    setStornierenModus(false);
    setStornierenGrund("");
  }

  const vormerkenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerken(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const zurueckziehenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerkungZurueckziehen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const buchenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.buchen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const stornierenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.buchungStornieren([...ausgewaehlteZeitIds], stornierenGrund),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });

  const gesamtSekunden = (zeiterfassungListe ?? []).reduce((summe, e) => {
    if (!e.ende_at) return summe;
    return summe + (new Date(e.ende_at).getTime() - new Date(e.start_at).getTime()) / 1000;
  }, 0);
  const gesamtStunden = formatSekundenAlsHHMM(gesamtSekunden);
  const gesamtKm = (zeiterfassungListe ?? []).reduce((summe, e) => summe + (Number(e.km) || 0), 0);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  // Buchungsablauf (Stufe 2, siehe docs/konzepte/ZEITERFASSUNG.md
  // Abschnitt 6.1/6.2) -- eine Zeile ist auswaehlbar, wenn sie zu einem der
  // Sammel-Endpunkte passt: vermerkt/vorgemerkt fuer eigene Eintraege oder
  // mit Buchungsrecht fuer beliebige, gebucht nur mit Buchungsrecht (fuer
  // "Buchung stornieren"). Alle ausgewaehlten Eintraege muessen denselben
  // Status haben, sonst waere unklar, welche Aktion gemeint ist.
  const darfZeitenBuchen = !!currentUser?.darf_zeiten_buchen;
  function kannZeitAuswaehlen(e: Zeiterfassung): boolean {
    const eigene = e.techniker_id === currentUser?.id;
    if (e.buchungsstatus === "vermerkt" || e.buchungsstatus === "vorgemerkt") {
      return eigene || darfZeitenBuchen;
    }
    if (e.buchungsstatus === "gebucht") {
      return darfZeitenBuchen;
    }
    return false;
  }
  const ausgewaehlteEintraege = (zeiterfassungListe ?? []).filter((e) => ausgewaehlteZeitIds.has(e.id));
  const ausgewaehlterStatus = ausgewaehlteEintraege[0]?.buchungsstatus ?? null;
  function zeitCheckboxToggeln(e: Zeiterfassung) {
    setAusgewaehlteZeitIds((bisherige) => {
      const neu = new Set(bisherige);
      if (neu.has(e.id)) {
        neu.delete(e.id);
      } else {
        // Nur Eintraege desselben Status gleichzeitig auswaehlbar.
        if (ausgewaehlterStatus && e.buchungsstatus !== ausgewaehlterStatus) neu.clear();
        neu.add(e.id);
      }
      return neu;
    });
  }
  async function handleBuchen() {
    const stunden = formatSekundenAlsHHMM(
      ausgewaehlteEintraege.reduce(
        (summe, e) => summe + (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000,
        0,
      ),
    );
    if (
      await bestaetigen(
        `${ausgewaehlteEintraege.length} Eintrag/Einträge mit insgesamt ${stunden} Std. buchen? Gebuchte Einträge kannst du danach nicht mehr ändern.`,
      )
    ) {
      buchenMutation.mutate([...ausgewaehlteZeitIds]);
    }
  }


  return {
    ausgewaehlteEintraege,
    ausgewaehlteZeitIds,
    ausgewaehlterStatus,
    buchenMutation,
    darfZeitenBuchen,
    gesamtKm,
    gesamtSekunden,
    gesamtStunden,
    handleBuchen,
    kannZeitAuswaehlen,
    laufenderTimer,
    nachBuchungsaktionAufraeumen,
    nachStoppenEintrag,
    nachStoppenTaetigkeit,
    nachStoppenTaetigkeitMutation,
    setAusgewaehlteZeitIds,
    setNachStoppenEintrag,
    setNachStoppenTaetigkeit,
    setStornierenGrund,
    setStornierenModus,
    setTaetigkeit,
    setZeitSheetModus,
    startTimerMutation,
    stopTimerMutation,
    stornierenGrund,
    stornierenModus,
    stornierenMutation,
    taetigkeit,
    timerLaeuftAnderswo,
    timerLaeuftHier,
    vormerkenMutation,
    zeitCheckboxToggeln,
    zeitSheetModus,
    zeiterfassungListe,
    zurueckziehenMutation,
  };
}

export type ZeitDaten = ReturnType<typeof useVorgangZeit>;
