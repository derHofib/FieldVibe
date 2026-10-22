import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError } from "../../../api/client";
import { highlightsApi, vorgaengeApi, vorgangEventsApi } from "../../../api/endpoints";
import { cacheEvents, getCachedEvents } from "../../../offline/cache";
import { getOutboxItems, queueDokument, queueFoto, queueKommentar } from "../../../offline/outbox";
import type { EmailLog, VorgangEvent } from "../../../types";

/** Verlauf: Kommentare, Fotos, Dokumente, Unterschrift, E-Mails und die Offline-Warteschlange. */
export function useVorgangVerlauf({
  id,
  meldeAktionsFehler,
  partnerKommentarMoeglich,
  setAktionsFehler,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
  partnerKommentarMoeglich: boolean;
  setAktionsFehler: (wert: string | null) => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dokumentInputRef = useRef<HTMLInputElement>(null);

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [anPartner, setAnPartner] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  // Verlauf-Filter: "system" = Statuswechsel/automatische Eintraege,
  // "kommentare" = alles Nutzergenerierte (Kommentar/Foto/Unterschrift/
  // Dokument), "email" = E-Mail-Verlauf -- rein clientseitig auf der
  // bereits geladenen Liste, kein eigener Endpunkt noetig.
  const [verlaufFilter, setVerlaufFilter] = useState<"alle" | "kommentare" | "system" | "email">("alle");
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [showUnterschriftPad, setShowUnterschriftPad] = useState(false);
  const { data: events } = useQuery({
    queryKey: ["vorgang-events", id],
    queryFn: async () => {
      try {
        const result = await vorgangEventsApi.list(id!);
        await cacheEvents(result);
        return result;
      } catch (err) {
        if (!navigator.onLine) return getCachedEvents(id!);
        throw err;
      }
    },
    enabled: !!id,
  });
  // Gleicher queryKey wie in der EmailSection (VerlaufInhalt) -- React Query
  // dedupliziert daher den Request, es wird trotz zwei useQuery-Aufrufen
  // nur einmal geladen.
  const { data: emails } = useQuery({
    queryKey: ["vorgang-emails", id],
    queryFn: () => vorgaengeApi.emails(id!),
    enabled: !!id,
  });
  const { data: outboxItems } = useQuery({
    queryKey: ["outbox", id],
    queryFn: () => getOutboxItems(id!),
    enabled: !!id,
  });
  const highlightMutation = useMutation({
    mutationFn: (eventId: number) => highlightsApi.create(eventId),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        setAktionsFehler("Dieses Foto ist bereits als Highlight markiert.");
      } else {
        meldeAktionsFehler(err);
      }
    },
  });

  const commentMutation = useMutation({
    mutationFn: async () => {
      try {
        return await vorgangEventsApi.create(id!, {
          event_type: "kommentar",
          body: comment,
          kundensichtbar,
          partner_sichtbar: partnerKommentarMoeglich && anPartner,
          client_uuid: crypto.randomUUID(),
        });
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueKommentar(id!, comment, kundensichtbar, partnerKommentarMoeglich && anPartner); // Netzwerkfehler -> offline
        return null;
      }
    },
    onSuccess: () => {
      setComment("");
      setKundensichtbar(false);
      setAnPartner(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
    onError: meldeAktionsFehler,
  });

  const fotoMutation = useMutation({
    mutationFn: async (file: File) => {
      const clientUuid = crypto.randomUUID();
      try {
        return await vorgangEventsApi.uploadFoto(
          id!,
          file,
          file.name,
          kundensichtbar,
          undefined,
          clientUuid,
        );
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueFoto(id!, file, file.name, kundensichtbar, clientUuid);
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
    onError: meldeAktionsFehler,
  });

  const dokumentMutation = useMutation({
    mutationFn: async (file: File) => {
      const clientUuid = crypto.randomUUID();
      try {
        return await vorgangEventsApi.uploadDokument(
          id!,
          file,
          file.name,
          kundensichtbar,
          undefined,
          clientUuid,
        );
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueDokument(id!, file, file.name, kundensichtbar, clientUuid);
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
    onError: meldeAktionsFehler,
  });

  const unterschriftMutation = useMutation({
    mutationFn: ({ blob, unterzeichnerName }: { blob: Blob; unterzeichnerName: string }) =>
      vorgangEventsApi.uploadUnterschrift(id!, blob, unterzeichnerName),
    onSuccess: () => {
      setShowUnterschriftPad(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  // Neuestes Ereignis oben, ältestes unten -- der Backend-Endpunkt liefert
  // bereits "ORDER BY id DESC" (siehe app/api/routes/vorgang_events.py),
  // hier also unveraendert uebernehmen statt umzudrehen.
  const sichtbareEvents = kundenansicht
    ? (events ?? []).filter((e) => e.kundensichtbar)
    : events ?? [];
  const eigeneOutboxItems = (outboxItems ?? []).filter((i) => i.vorgang_id === id);

  // E-Mails laufen im gemeinsamen Verlauf mit den Kommentaren statt in einer
  // eigenen Box (siehe Design-Vorschlag). Nur in der internen Ansicht: das
  // Kundenportal kennt EmailLog nicht, die "Kundenansicht"-Vorschau soll
  // deshalb nicht mehr zeigen, als der Kunde dort tatsaechlich sieht.
  type VerlaufEintrag = { art: "event"; zeit: string; event: VorgangEvent } | { art: "email"; zeit: string; email: EmailLog };
  const verlaufEintraege: VerlaufEintrag[] = [
    ...sichtbareEvents.map((event): VerlaufEintrag => ({ art: "event", zeit: event.created_at, event })),
    ...(kundenansicht ? [] : (emails ?? []).map((email): VerlaufEintrag => ({ art: "email", zeit: email.created_at, email }))),
  ].sort((a, b) => new Date(b.zeit).getTime() - new Date(a.zeit).getTime());
  const verlaufEintraegeGefiltert = verlaufEintraege.filter((eintrag) => {
    if (verlaufFilter === "alle") return true;
    if (eintrag.art === "email") return verlaufFilter === "email";
    if (verlaufFilter === "system") return eintrag.event.is_system || eintrag.event.event_type === "status_change";
    // "kommentare": alles Nutzergenerierte -- Kommentar, Foto, Unterschrift, Dokument.
    return !eintrag.event.is_system && eintrag.event.event_type !== "status_change";
  });
  const eigeneOutboxItemsGefiltert = eigeneOutboxItems.filter((item) => {
    if (verlaufFilter === "alle") return true;
    if (verlaufFilter === "email") return false; // Outbox kennt keine E-Mails.
    if (verlaufFilter === "system") return item.kind === "status";
    return item.kind !== "status";
  });


  return {
    anPartner,
    comment,
    commentMutation,
    dokumentInputRef,
    dokumentMutation,
    eigeneOutboxItems,
    eigeneOutboxItemsGefiltert,
    emails,
    events,
    fileInputRef,
    fotoMutation,
    highlightMutation,
    kundenansicht,
    kundensichtbar,
    outboxItems,
    setAnPartner,
    setComment,
    setKundenansicht,
    setKundensichtbar,
    setShowMentionPicker,
    setShowUnterschriftPad,
    setVerlaufFilter,
    showMentionPicker,
    showUnterschriftPad,
    sichtbareEvents,
    unterschriftMutation,
    verlaufEintraege,
    verlaufEintraegeGefiltert,
    verlaufFilter,
  };
}

export type VerlaufDaten = ReturnType<typeof useVorgangVerlauf>;
