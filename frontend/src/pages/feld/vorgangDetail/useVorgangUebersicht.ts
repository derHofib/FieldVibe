import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "../../../api/client";
import { anlagenApi, kundenApi, mandantEinstellungenApi, vorgaengeApi } from "../../../api/endpoints";
import { queueStatusChange } from "../../../offline/outbox";
import type { Leistungstyp, Vorgang, VorgangStatus } from "../../../types";
import { leereAdresse } from "./helfer";

/** Kopfbereich: Zuordnung (Kunde/Anlage), Adresse, Status, Priorität, Folge-Vorgang und Übernahme. */
export function useVorgangUebersicht({
  id,
  meldeAktionsFehler,
  vorgang,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
  vorgang: Vorgang | undefined;
}) {
  const queryClient = useQueryClient();
  const [editingZuordnung, setEditingZuordnung] = useState(false);
  const [editKundeId, setEditKundeId] = useState("");
  const [editAnlageId, setEditAnlageId] = useState("");
  const [zuordnungError, setZuordnungError] = useState<string | null>(null);
  const [editingAdresse, setEditingAdresse] = useState(false);
  const [adresseForm, setAdresseForm] = useState(() => leereAdresse(null));
  const [adresseError, setAdresseError] = useState<string | null>(null);
  const [showWartetKundeDialog, setShowWartetKundeDialog] = useState(false);
  const [wiedervorlageTage, setWiedervorlageTage] = useState("");
  const [showFolgeAuftragDialog, setShowFolgeAuftragDialog] = useState(false);
  const [folgeAuftragLeistungstyp, setFolgeAuftragLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [folgeVorgangId, setFolgeVorgangId] = useState<string | null>(null);
  const { data: parentVorgang } = useQuery({
    queryKey: ["vorgang", vorgang?.parent_vorgang_id],
    queryFn: () => vorgaengeApi.get(vorgang!.parent_vorgang_id!),
    enabled: !!vorgang?.parent_vorgang_id,
  });
  const { data: folgeAuftraege } = useQuery({
    queryKey: ["vorgaenge", "folge", id],
    queryFn: () => vorgaengeApi.list({ parent_vorgang_id: id! }),
    enabled: !!id,
  });
  const { data: mandantEinstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    enabled: showWartetKundeDialog,
  });
  const { data: weitereAnlagen } = useQuery({
    queryKey: ["vorgang-anlagen", id],
    queryFn: () => vorgaengeApi.anlagen(id!),
    enabled: !!id,
  });
  const [showAnlageHinzufuegen, setShowAnlageHinzufuegen] = useState(false);
  const [neueAnlageId, setNeueAnlageId] = useState("");
  const { data: anlagenFuerVorgangKunde } = useQuery({
    queryKey: ["anlagen", vorgang?.kunde_id],
    queryFn: () => anlagenApi.list(vorgang!.kunde_id, undefined, true),
    enabled: showAnlageHinzufuegen && !!vorgang?.kunde_id,
  });
  const bereitsZugeordneteAnlageIds = new Set([
    ...(weitereAnlagen ?? []).map((a) => a.id),
    ...(vorgang?.anlage_id ? [vorgang.anlage_id] : []),
  ]);
  const anlageHinzufuegenMutation = useMutation({
    mutationFn: (anlageId: string) => vorgaengeApi.anlagenHinzufuegen(id!, [anlageId]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-anlagen", id] });
      setShowAnlageHinzufuegen(false);
      setNeueAnlageId("");
    },
    onError: meldeAktionsFehler,
  });
  const anlageEntfernenMutation = useMutation({
    mutationFn: (anlageId: string) => vorgaengeApi.anlageEntfernen(id!, anlageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang-anlagen", id] }),
    onError: meldeAktionsFehler,
  });
  const { data: alleKunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: editingZuordnung,
  });
  const { data: anlagenFuerEditKunde } = useQuery({
    queryKey: ["anlagen", editKundeId],
    queryFn: () => anlagenApi.list(editKundeId),
    enabled: editingZuordnung && !!editKundeId,
  });
  const zuordnungMutation = useMutation({
    mutationFn: () =>
      vorgaengeApi.update(id!, { kunde_id: editKundeId, anlage_id: editAnlageId || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      setEditingZuordnung(false);
      setZuordnungError(null);
    },
    onError: (err) =>
      setZuordnungError(
        err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
      ),
  });
  const adresseMutation = useMutation({
    mutationFn: () =>
      vorgaengeApi.update(id!, {
        adresse:
          adresseForm.strasse || adresseForm.plz || adresseForm.ort
            ? {
                strasse: adresseForm.strasse || undefined,
                plz: adresseForm.plz || undefined,
                ort: adresseForm.ort || undefined,
              }
            : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      setEditingAdresse(false);
      setAdresseError(null);
    },
    onError: (err) =>
      setAdresseError(
        err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
      ),
  });
  const statusMutation = useMutation({
    mutationFn: async ({
      status,
      wiedervorlageTage,
    }: {
      status: VorgangStatus;
      wiedervorlageTage?: number;
    }) => {
      try {
        return await vorgaengeApi.update(id!, {
          status,
          ...(wiedervorlageTage ? { wiedervorlage_tage: wiedervorlageTage } : {}),
        });
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueStatusChange(id!, status); // Netzwerkfehler -> offline
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
    onError: meldeAktionsFehler,
  });

  const folgeAuftragMutation = useMutation({
    mutationFn: (leistungstyp: Leistungstyp) => vorgaengeApi.folgeAuftrag(id!, leistungstyp),
    onSuccess: (result) => {
      setFolgeVorgangId(result.id);
      queryClient.invalidateQueries({ queryKey: ["vorgaenge", "folge", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const uebernehmenMutation = useMutation({
    mutationFn: () => vorgaengeApi.uebernehmen(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const prioritaetMutation = useMutation({
    mutationFn: (prioritaet: number) => vorgaengeApi.update(id!, { prioritaet }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang", id] }),
    onError: meldeAktionsFehler,
  });


  return {
    adresseError,
    adresseForm,
    adresseMutation,
    alleKunden,
    anlageEntfernenMutation,
    anlageHinzufuegenMutation,
    anlagenFuerEditKunde,
    anlagenFuerVorgangKunde,
    bereitsZugeordneteAnlageIds,
    editAnlageId,
    editKundeId,
    editingAdresse,
    editingZuordnung,
    folgeAuftraege,
    folgeAuftragLeistungstyp,
    folgeAuftragMutation,
    folgeVorgangId,
    mandantEinstellungen,
    neueAnlageId,
    parentVorgang,
    prioritaetMutation,
    setAdresseError,
    setAdresseForm,
    setEditAnlageId,
    setEditKundeId,
    setEditingAdresse,
    setEditingZuordnung,
    setFolgeAuftragLeistungstyp,
    setFolgeVorgangId,
    setNeueAnlageId,
    setShowAnlageHinzufuegen,
    setShowFolgeAuftragDialog,
    setShowWartetKundeDialog,
    setWiedervorlageTage,
    setZuordnungError,
    showAnlageHinzufuegen,
    showFolgeAuftragDialog,
    showWartetKundeDialog,
    statusMutation,
    uebernehmenMutation,
    weitereAnlagen,
    wiedervorlageTage,
    zuordnungError,
    zuordnungMutation,
  };
}

export type UebersichtDaten = ReturnType<typeof useVorgangUebersicht>;
