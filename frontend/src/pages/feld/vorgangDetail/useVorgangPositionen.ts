import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  angeboteApi, anlagenApi, fahrzeugZuweisungenApi, leistungsverzeichnisApi, lieferantenApi,
  materialApi, materialBedarfeApi, rechnungenApi,
} from "../../../api/endpoints";
import { useAuth } from "../../../context/AuthContext";
import type { Kunde, MaterialBedarfZweck, Vorgang } from "../../../types";
import { NEU_MATERIAL } from "./konstanten";

/** Positionen: Material (Bedarf/Verwendung), Leistungen aus dem Leistungsverzeichnis, Angebot/Rechnung aus dem Vorgang. */
export function useVorgangPositionen({
  id,
  kunde,
  meldeAktionsFehler,
  vorgang,
}: {
  id: string | undefined;
  kunde: Kunde | undefined;
  meldeAktionsFehler: (err: unknown) => void;
  vorgang: Vorgang | undefined;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [showMaterialForm, setShowMaterialForm] = useState(false);
  const [materialId, setMaterialId] = useState("");
  const [materialMenge, setMaterialMenge] = useState("");
  const [materialLagerId, setMaterialLagerId] = useState("");
  const [showLeistungForm, setShowLeistungForm] = useState(false);
  const [lvPositionId, setLvPositionId] = useState("");
  const [lvMenge, setLvMenge] = useState("");
  const [showBedarfForm, setShowBedarfForm] = useState(false);
  const [bedarfMaterialId, setBedarfMaterialId] = useState("");
  const [bedarfMenge, setBedarfMenge] = useState("");
  const [bedarfZweck, setBedarfZweck] = useState<MaterialBedarfZweck>("bestellung");
  const [bedarfNotiz, setBedarfNotiz] = useState("");
  const [bedarfNeuBezeichnung, setBedarfNeuBezeichnung] = useState("");
  const [bedarfNeuEinheit, setBedarfNeuEinheit] = useState("Stk");
  const [bedarfNeuEinzelpreis, setBedarfNeuEinzelpreis] = useState("");
  const [bedarfNeuLieferantId, setBedarfNeuLieferantId] = useState("");
  const angebotAusVorgangMutation = useMutation({
    mutationFn: () => angeboteApi.createFromVorgang(id!),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
    onError: meldeAktionsFehler,
  });

  const rechnungAusVorgangMutation = useMutation({
    mutationFn: () => rechnungenApi.create({ kunde_id: vorgang!.kunde_id, vorgang_id: id }),
    onSuccess: (rechnung) => navigate(`/rechnungen/${rechnung.id}`),
    onError: meldeAktionsFehler,
  });

  const { data: materialListe } = useQuery({ queryKey: ["material"], queryFn: () => materialApi.list() });
  const { data: alleAnlagenFuerLager } = useQuery({
    queryKey: ["lagerorte"],
    queryFn: () => anlagenApi.list(),
    enabled: showMaterialForm,
  });
  const lagerorte = (alleAnlagenFuerLager ?? []).filter((a) => a.objekttyp !== "kundenanlage");
  const { data: meinFahrzeug } = useQuery({
    queryKey: ["fahrzeug-mir"],
    queryFn: fahrzeugZuweisungenApi.mir,
    enabled: showMaterialForm && !!currentUser?.nur_zugewiesene_kunden,
  });

  const materialVerwendenMutation = useMutation({
    mutationFn: () => materialApi.verwenden(materialId, id!, materialLagerId, materialMenge),
    onSuccess: () => {
      setShowMaterialForm(false);
      setMaterialId("");
      setMaterialMenge("");
      setMaterialLagerId("");
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["material-verwendungen", "vorgang", id] });
    },
    onError: meldeAktionsFehler,
  });

  const { data: leistungsverzeichnis } = useQuery({
    queryKey: ["leistungsverzeichnis", kunde?.id],
    queryFn: () => leistungsverzeichnisApi.list(kunde!.id),
    enabled: showLeistungForm && !!kunde,
  });

  const leistungVerwendenMutation = useMutation({
    mutationFn: () => leistungsverzeichnisApi.verwenden(lvPositionId, id!, lvMenge),
    onSuccess: () => {
      setShowLeistungForm(false);
      setLvPositionId("");
      setLvMenge("");
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id] });
    },
    onError: meldeAktionsFehler,
  });

  const lvVerwendungEntfernenMutation = useMutation({
    mutationFn: (verwendungId: string) => leistungsverzeichnisApi.verwendungEntfernen(verwendungId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  useEffect(() => {
    if (showBedarfForm && vorgang) {
      setBedarfZweck(vorgang.leistungstyp === "planung" || vorgang.leistungstyp === "beratung" ? "angebot" : "bestellung");
    }
  }, [showBedarfForm, vorgang]);

  const { data: materialBedarfe } = useQuery({
    queryKey: ["material-bedarfe", "vorgang", id],
    queryFn: () => materialBedarfeApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });
  const { data: materialVerwendungen } = useQuery({
    queryKey: ["material-verwendungen", "vorgang", id],
    queryFn: () => materialApi.verwendungen(id!),
    enabled: !!id,
  });
  const { data: lvVerwendungen } = useQuery({
    queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id],
    queryFn: () => leistungsverzeichnisApi.verwendungen(id!),
    enabled: !!id,
  });
  const { data: lieferantenFuerNeuesMaterial } = useQuery({
    queryKey: ["lieferanten"],
    queryFn: () => lieferantenApi.list(),
    enabled: showBedarfForm && bedarfMaterialId === NEU_MATERIAL,
  });

  const materialBedarfMutation = useMutation({
    mutationFn: async () => {
      // Wenn das Material noch nicht im Katalog existiert (haeufiger Fall
      // bei einer Erstbestellung), wird es hier mit Bestand 0 angelegt --
      // der Bedarf haengt sich danach an den neuen Katalogeintrag, statt
      // eine eigene Freitext-Ablage zu brauchen.
      const materialId =
        bedarfMaterialId === NEU_MATERIAL
          ? (
              await materialApi.create({
                bezeichnung: bedarfNeuBezeichnung,
                einheit: bedarfNeuEinheit,
                einzelpreis: bedarfNeuEinzelpreis || undefined,
                lieferant_id: bedarfNeuLieferantId || undefined,
              })
            ).id
          : bedarfMaterialId;
      return materialBedarfeApi.create({
        material_id: materialId,
        vorgang_id: id!,
        menge: bedarfMenge,
        zweck: bedarfZweck,
        notiz: bedarfNotiz || undefined,
      });
    },
    onSuccess: () => {
      setShowBedarfForm(false);
      setBedarfMaterialId("");
      setBedarfMenge("");
      setBedarfNotiz("");
      setBedarfNeuBezeichnung("");
      setBedarfNeuEinheit("Stk");
      setBedarfNeuEinzelpreis("");
      setBedarfNeuLieferantId("");
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
    },
    onError: meldeAktionsFehler,
  });

  const bedarfEntfernenMutation = useMutation({
    mutationFn: (bedarfId: string) => materialBedarfeApi.remove(bedarfId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const positionenAnzahl =
    (materialBedarfe?.length ?? 0) + (materialVerwendungen?.length ?? 0) + (lvVerwendungen?.length ?? 0);


  return {
    alleAnlagenFuerLager,
    angebotAusVorgangMutation,
    bedarfEntfernenMutation,
    bedarfMaterialId,
    bedarfMenge,
    bedarfNeuBezeichnung,
    bedarfNeuEinheit,
    bedarfNeuEinzelpreis,
    bedarfNeuLieferantId,
    bedarfNotiz,
    bedarfZweck,
    lagerorte,
    leistungVerwendenMutation,
    leistungsverzeichnis,
    lieferantenFuerNeuesMaterial,
    lvMenge,
    lvPositionId,
    lvVerwendungEntfernenMutation,
    lvVerwendungen,
    materialBedarfMutation,
    materialBedarfe,
    materialId,
    materialLagerId,
    materialListe,
    materialMenge,
    materialVerwendenMutation,
    materialVerwendungen,
    meinFahrzeug,
    positionenAnzahl,
    rechnungAusVorgangMutation,
    setBedarfMaterialId,
    setBedarfMenge,
    setBedarfNeuBezeichnung,
    setBedarfNeuEinheit,
    setBedarfNeuEinzelpreis,
    setBedarfNeuLieferantId,
    setBedarfNotiz,
    setBedarfZweck,
    setLvMenge,
    setLvPositionId,
    setMaterialId,
    setMaterialLagerId,
    setMaterialMenge,
    setShowBedarfForm,
    setShowLeistungForm,
    setShowMaterialForm,
    showBedarfForm,
    showLeistungForm,
    showMaterialForm,
  };
}

export type PositionenDaten = ReturnType<typeof useVorgangPositionen>;
