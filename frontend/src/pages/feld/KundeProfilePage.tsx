import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kundeTypLabel } from "../../config/kundeDarstellung";
import { Download, MoreHorizontal, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { kundenApi, standorteApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { PulldownMenu, type PulldownItem } from "../../components/apple/PulldownMenu";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { downloadBlob } from "../../utils/download";
import type { Anlage } from "../../types";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";
import { KundeUebersichtTab } from "./kunde/KundeUebersichtTab";
import { KundeKommunikationTab } from "./kunde/KundeKommunikationTab";
import { KundeAnlagenTab } from "./kunde/KundeAnlagenTab";
import { KundeVorgaengeTab } from "./kunde/KundeVorgaengeTab";

type KundeTab = "uebersicht" | "vorgaenge" | "anlagen" | "kommunikation";
const KUNDE_TABS: KundeTab[] = ["uebersicht", "vorgaenge", "anlagen", "kommunikation"];

/** `id`/`eingebettet` nur für das Detailpanel der Office-Kundenliste
 * (office/kunden): dort fehlt die Route, und "Zurück" ergibt keinen Sinn. */
export function KundeProfilePage({
  id: idProp,
  eingebettet = false,
}: { id?: string; eingebettet?: boolean } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const [anlageFilter, setAnlageFilter] = useState("");
  // Aktiver Tab im Query-Parameter, damit Reload/Deep-Link denselben Tab zeigen.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: KundeTab = KUNDE_TABS.includes(tabParam as KundeTab) ? (tabParam as KundeTab) : "uebersicht";

  const kundenverwaltungAktiv = istModulAktiv(currentUser, "kundenverwaltung");

  const { data: profil, isLoading: profilLoading, error: profilFehler, refetch: profilNeu } = useQuery({
    queryKey: ["kunde-profil", id],
    queryFn: () => kundenApi.profil(id!),
    enabled: !!id && kundenverwaltungAktiv,
  });

  const { data: kunde, isLoading: kundeLoading } = useQuery({
    queryKey: ["kunde", id],
    queryFn: () => kundenApi.get(id!),
    enabled: !!id && !kundenverwaltungAktiv,
  });

  const { data: standorteFuerAnlagen } = useQuery({
    queryKey: ["standorte", id],
    queryFn: () => standorteApi.list(id!),
    enabled: !!id && kundenverwaltungAktiv,
  });

  const anlageNameById = useMemo(
    () => new Map((profil?.anlagen ?? []).map((a: Anlage) => [a.id, a.bezeichnung])),
    [profil?.anlagen]
  );
  const sichtbareVorgaenge = useMemo(
    () =>
      anlageFilter
        ? (profil?.vorgaenge ?? []).filter((v) => v.anlage_id === anlageFilter)
        : profil?.vorgaenge ?? [],
    [profil?.vorgaenge, anlageFilter]
  );

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => kundenApi.remove(id!),
    onSuccess: () => navigate("/kunden"),
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  const datenexportMutation = useMutation({
    mutationFn: () => kundenApi.datenexport(id!),
    onSuccess: (blob) => downloadBlob(blob, `Datenexport-${kunde?.name ?? profil?.name ?? id}.json`),
  });

  if (!kundenverwaltungAktiv) {
    if (kundeLoading || !kunde) return <DetailSkeleton />;
    return (
      <div className="space-y-4">
        {!eingebettet && (
          <button onClick={() => navigate(-1)} className="text-sm text-label2">
            ← Zurück
          </button>
        )}
        <div className="card-ap p-4">
          <div className="text-xs text-label2">{kunde.kundennummer}</div>
          <h1 className="text-lg font-bold text-label">{kunde.name}</h1>
          {kunde.typ && <span className="text-sm text-label2">{kundeTypLabel(kunde.typ)}</span>}
        </div>
      </div>
    );
  }

  if (profilFehler && !profil)
    return <FehlerZustand fehler={profilFehler} was="Der Kunde" zurueck onErneut={() => void profilNeu()} className="py-6" />;
  if (profilLoading || !profil) return <DetailSkeleton />;

  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const kannLoeschen = hatRecht("kunden", "loeschen");
  const menueEintraege: PulldownItem[] = [
    ...(kannVerwalten
      ? [
          {
            label: "Datenexport (DSGVO)",
            icon: Download,
            onSelect: () => datenexportMutation.mutate(),
          },
        ]
      : []),
    ...(kannLoeschen
      ? [
          ...(kannVerwalten ? ["trenner" as const] : []),
          {
            label: "Kunde löschen",
            icon: Trash2,
            destruktiv: true,
            onSelect: async () => {
              if (await bestaetigen({ titel: `${profil.name} löschen?`, text: `Das kann nicht rückgängig gemacht werden.`, bestaetigenLabel: "Löschen" })) {
                deleteMutation.mutate();
              }
            },
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-4">
      {!eingebettet && (
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
      )}

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">{profil.kundennummer}</div>
            <h1 className="text-lg font-bold text-label">{profil.name}</h1>
            {profil.typ && <span className="text-sm text-label2">{kundeTypLabel(profil.typ)}</span>}
          </div>
          {menueEintraege.length > 0 && (
            <PulldownMenu
              ariaLabel="Weitere Aktionen"
              items={menueEintraege}
              trigger={({ offen, toggeln, triggerRef }) => (
                <button
                  ref={triggerRef}
                  type="button"
                  onClick={toggeln}
                  aria-haspopup="menu"
                  aria-expanded={offen}
                  aria-label="Weitere Aktionen"
                  className="btn-touch flex items-center justify-center text-label2"
                >
                  <MoreHorizontal size={20} strokeWidth={2} aria-hidden="true" />
                </button>
              )}
            />
          )}
        </div>
        {deleteError && <p className="mt-2 text-sm text-st-fehlt ">{deleteError}</p>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-xs text-label">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <SegmentedControl
        ariaLabel="Kundenprofil"
        groesse="touch"
        volleBreite
        wert={tab}
        optionen={[
          { wert: "uebersicht", label: "Übersicht" },
          { wert: "vorgaenge", label: `Vorgänge${profil.vorgaenge.length > 0 ? ` (${profil.vorgaenge.length})` : ""}` },
          { wert: "anlagen", label: `Anlagen${profil.anlagen.length > 0 ? ` (${profil.anlagen.length})` : ""}` },
          { wert: "kommunikation", label: "Kontakt" },
        ]}
        onChange={(key) => setSearchParams(key === "uebersicht" ? {} : { tab: key }, { replace: true })}
      />

      {tab === "uebersicht" && (
      <KundeUebersichtTab
        id={id}
        profil={profil}
        kannVerwalten={kannVerwalten}
      />
      )}

      {tab === "kommunikation" && (
      <KundeKommunikationTab
        profil={profil}
        kannVerwalten={kannVerwalten}
        id={id}
        queryClient={queryClient}
        currentUser={currentUser}
      />
      )}

      {tab === "anlagen" && (
      <KundeAnlagenTab
        id={id}
        kannVerwalten={kannVerwalten}
        profil={profil}
        navigate={navigate}
        standorteFuerAnlagen={standorteFuerAnlagen}
      />
      )}

      {tab === "vorgaenge" && (
      <KundeVorgaengeTab
        kannVerwalten={kannVerwalten}
        id={id}
        profil={profil}
        anlageFilter={anlageFilter}
        setAnlageFilter={setAnlageFilter}
        sichtbareVorgaenge={sichtbareVorgaenge}
        navigate={navigate}
        anlageNameById={anlageNameById}
      />
      )}
    </div>
  );
}
