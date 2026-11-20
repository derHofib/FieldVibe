import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { papierkorbApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../api/client";
import type { PapierkorbEintrag, PapierkorbEntityTyp } from "../../types";
import { AktionsMenue } from "../../components/AktionsMenue";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { SkeletonList } from "../../components/Skeleton";
import { Select } from "../../components/apple/Select";

// Muss mit ENTITY_REGISTRY in backend/app/services/papierkorb_service.py
// uebereinstimmen.
const ENTITY_TYP_LABEL: Record<PapierkorbEntityTyp, string> = {
  kunde: "Kunde",
  anlage: "Anlage",
  vertrag: "Vertrag",
  vorgang: "Vorgang",
  standort: "Standort",
  termin: "Termin",
  pruefzyklus: "Prüfzyklus",
  pruefmittel: "Prüfmittel",
  lieferant: "Lieferant",
  material: "Material",
  material_bedarf: "Materialbedarf",
  bestellung: "Bestellung",
  dauerauftrag: "Dauerauftrag",
  dauerauftrag_ziel: "Dauerauftrag-Ziel",
  mangel: "Mangel",
  angebot: "Angebot",
  rechnung: "Rechnung",
  inventurzyklus: "Inventurzyklus",
  fahrzeug_zuweisung: "Fahrzeug-Zuweisung",
  tag: "Tag",
  vorgang_anfrage: "Vorgangsanfrage",
  vor_ort_kontakt: "Kontakt vor Ort",
};

function formatDatum(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function anzeigeName(eintrag: PapierkorbEintrag): string {
  if (eintrag.titel) return eintrag.titel;
  return `${ENTITY_TYP_LABEL[eintrag.entity_typ]} ${eintrag.id.slice(0, 8)}`;
}

export function PapierkorbPage() {
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<PapierkorbEntityTyp | "">("");
  const [fehler, setFehler] = useState<string | null>(null);

  const istOperativ = currentUser?.role === "loesch_operativ";

  const { data: eintraege, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["papierkorb", filter],
    queryFn: () => papierkorbApi.list(filter || undefined),
  });

  const restoreMutation = useMutation({
    meta: { erfolg: "Wiederhergestellt" },
    mutationFn: (eintrag: PapierkorbEintrag) =>
      papierkorbApi.wiederherstellen(eintrag.entity_typ, eintrag.id),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["papierkorb"] });
    },
    onError: () => setFehler("Wiederherstellen fehlgeschlagen"),
  });

  const purgeMutation = useMutation({
    meta: { erfolg: "Endgültig gelöscht" },
    mutationFn: (eintrag: PapierkorbEintrag) =>
      papierkorbApi.endgueltigLoeschen(eintrag.entity_typ, eintrag.id),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["papierkorb"] });
    },
    onError: (err) =>
      setFehler(
        err instanceof ApiError
          ? err.message
          : "Endgültiges Löschen fehlgeschlagen – vermutlich verweisen noch andere Daten darauf.",
      ),
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
          ← Zurück
        </button>
        <h1 className="text-titel-mobil font-bold text-label">Papierkorb</h1>
      </div>

      <p className="text-sekundaer text-label2">
        {istOperativ
          ? "Gelöschte Datensätze können hier wiederhergestellt oder endgültig entfernt werden."
          : "Nur-Ansicht: Wiederherstellen und endgültiges Löschen sind der Rolle „Papierkorb (operativ)“ vorbehalten."}
      </p>

      {fehler && <p className="text-fliess text-st-fehlt ">{fehler}</p>}

      <div>
        <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">
          Nach Typ filtern
        </label>
        <Select className="w-auto" id={`${uid}-0`}
          value={filter}
          onChange={(e) => setFilter(e.target.value as PapierkorbEntityTyp | "")}
        >
          <option value="">Alle Typen</option>
          {Object.entries(ENTITY_TYP_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !eintraege ? (
        <FehlerZustand fehler={ladeFehler} was="Der Papierkorb" onErneut={() => void neuLaden()} />
      ) : !eintraege || eintraege.length === 0 ? (
        <EmptyState
          icon={Trash2}
          text={filter ? "Keine gelöschten Einträge dieses Typs." : "Der Papierkorb ist leer. Gelöschte Datensätze erscheinen hier."}
        />
      ) : (
        <ul className="space-y-2">
          {eintraege.map((eintrag) => (
            <li
              key={`${eintrag.entity_typ}-${eintrag.id}`}
              className="flex items-center justify-between gap-3 card-ap p-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta font-semibold text-label">
                    {ENTITY_TYP_LABEL[eintrag.entity_typ]}
                  </span>
                  <span className="truncate font-medium text-label">
                    {anzeigeName(eintrag)}
                  </span>
                </div>
                <p className="mt-0.5 text-meta text-label2">
                  Gelöscht am {formatDatum(eintrag.geloescht_am)}
                  {eintrag.geloescht_von_name ? ` von ${eintrag.geloescht_von_name}` : ""}
                </p>
              </div>
              {istOperativ && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => restoreMutation.mutate(eintrag)}
                    disabled={restoreMutation.isPending}
                    className="btn-touch btn-ap px-3 text-sekundaer font-medium disabled:opacity-50"
                  >
                    Wiederherstellen
                  </button>
                  <AktionsMenue
                    label={`Aktionen für ${anzeigeName(eintrag)}`}
                    eintraege={[
                      {
                        label: "Endgültig löschen",
                        destruktiv: true,
                        disabled: purgeMutation.isPending,
                        onClick: async () => {
                          if (
                            await bestaetigen({ titel: `„${anzeigeName(eintrag)}“ endgültig löschen?`, text: `Das kann nicht rückgängig gemacht werden.`, bestaetigenLabel: "Endgültig löschen" })
                          ) {
                            purgeMutation.mutate(eintrag);
                          }
                        },
                      },
                    ]}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
