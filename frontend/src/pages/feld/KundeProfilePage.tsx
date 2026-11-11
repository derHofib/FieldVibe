import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kundeTypLabel } from "../../config/kundeDarstellung";
import { statusLabel } from "../../config/vorgangDarstellung";
import { Boxes, Download, Inbox, MoreHorizontal, Repeat, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { kundenApi, standorteApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnsprechpartnerVerwaltung } from "../../components/AnsprechpartnerVerwaltung";
import { PulldownMenu, type PulldownItem } from "../../components/apple/PulldownMenu";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { downloadBlob } from "../../utils/download";
import type { Anlage } from "../../types";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";
import { Stammdaten, TechnikerZuweisung } from "./kunde/KundeUebersicht";
import { AnlageAktivToggle, NeueAnlage } from "./kunde/KundeAnlagen";
import { StandorteVerwaltung } from "./kunde/KundeStandorte";
import { LeistungsverzeichnisVerwaltung } from "./kunde/KundeLeistungsverzeichnis";
import { KundenPortalLinkUndLogo, PortalZugaengeVerwaltung } from "./kunde/KundePortalZugaenge";
import { DauerauftraegeUebersicht } from "./kunde/DauerauftraegeUebersicht";

const STATUS_BADGE: Record<string, string> = {
  neu: "border border-tint text-tint ",
  geplant: "border border-purple-400 text-purple-700 dark:border-purple-600 dark:text-purple-300",
  in_arbeit: "border border-st-arbeit text-st-arbeit ",
  wartet_kunde: "border border-st-wartet text-st-wartet",
  abgeschlossen: "border border-st-erledigt text-st-erledigt ",
  abgerechnet: "border border-sep text-label ",
  storniert: "border border-sep text-label2",
};

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
              <span key={t.id} className="border border-sep px-2 py-0.5 text-xs text-label">
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
      <>
      <Stammdaten
        kundeId={id!}
        adresse={profil.adresse}
        notiz={profil.notiz}
        typ={profil.typ}
        ustIdnr={profil.ust_idnr}
        ust13bBis={profil.ust_13b_nachweis_bis ?? null}
        leitwegId={profil.leitweg_id ?? null}
        eRechnungFormat={profil.e_rechnung_format ?? null}
        debitorenkonto={profil.debitorenkonto ?? null}
        kannVerwalten={kannVerwalten}
      />

      {kannVerwalten && <TechnikerZuweisung kundeId={id!} zugewiesen={profil.techniker} />}
      </>
      )}

      {tab === "kommunikation" && (
      <>
      <AnsprechpartnerVerwaltung
        liste={profil.ansprechpartner}
        kannVerwalten={kannVerwalten}
        onSpeichern={async (naechsteListe) => {
          await kundenApi.update(id!, { ansprechpartner: naechsteListe });
          queryClient.invalidateQueries({ queryKey: ["kunde-profil", id] });
        }}
      />

      {kannVerwalten && (
        <EmailSection
          queryKey={["kunde-emails", id]}
          listEmails={() => kundenApi.emails(id!)}
          sendEmail={(body) =>
            kundenApi.sendEmail(id!, {
              empfaenger: body.empfaenger,
              betreff: body.betreff ?? "",
              inhalt: body.inhalt ?? "",
            })
          }
          defaultEmpfaenger={profil.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        />
      )}

      {kannVerwalten && istModulAktiv(currentUser, "kundenportal") && (
        <>
          <KundenPortalLinkUndLogo kunde={profil} />
          <PortalZugaengeVerwaltung kundeId={id!} />
        </>
      )}
      </>
      )}

      {tab === "anlagen" && (
      <>
      <StandorteVerwaltung kundeId={id!} kannVerwalten={kannVerwalten} />

      <LeistungsverzeichnisVerwaltung kundeId={id!} kundeName={profil.name} kannVerwalten={kannVerwalten} />

      <div>
        <h2 className="mb-2 text-sm font-semibold text-label2">Anlagen</h2>
        {profil.anlagen.length === 0 ? (
          <EmptyState icon={Boxes} text="Keine Anlagen." className="py-4" />
        ) : (
          <div className="space-y-2">
            {profil.anlagen.map((a) => (
              <div
                key={a.id}
                className={`flex items-center justify-between card-ap p-3 ${
                  a.aktiv ? "" : "opacity-60"
                }`}
              >
                <button onClick={() => navigate(`/anlagen/${a.id}`)} className="btn-touch flex-1 text-left">
                  <div className="text-sm font-medium text-label">{a.bezeichnung}</div>
                  {a.anlagentyp && <div className="text-xs text-label2">{a.anlagentyp}</div>}
                </button>
                {kannVerwalten && (
                  <AnlageAktivToggle anlage={a} kundeId={id!} />
                )}
              </div>
            ))}
          </div>
        )}
        {kannVerwalten && (
          <div className="mt-2">
            <NeueAnlage
              kundeId={id!}
              standorte={(standorteFuerAnlagen ?? []).filter((s) => s.aktiv)}
            />
          </div>
        )}
      </div>

      </>
      )}

      {tab === "vorgaenge" && (
      <>
      {kannVerwalten && <DauerauftraegeUebersicht kundeId={id!} />}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Vorgänge</h2>
          {profil.anlagen.length > 0 && (
            <select
              value={anlageFilter}
              onChange={(e) => setAnlageFilter(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-2 py-1 text-xs text-label"
            >
              <option value="">Alle Anlagen</option>
              {profil.anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
          )}
        </div>
        {sichtbareVorgaenge.length === 0 ? (
          <EmptyState icon={Inbox} text="Keine Vorgänge." className="py-4" />
        ) : (
          <div className="space-y-2">
            {sichtbareVorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className={`card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-label2">
                    {v.vorgangsnummer}
                    {v.anlage_id && anlageNameById.get(v.anlage_id) && ` · ${anlageNameById.get(v.anlage_id)}`}
                    {v.dauerauftrag_id && (
                      <>
                        {" · "}
                        <Repeat size={11} strokeWidth={2} className="inline text-st-arbeit" />
                      </>
                    )}
                  </div>
                  <div className="text-sm font-medium text-label">{v.titel}</div>
                </div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {statusLabel(v.status)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      </>
      )}
    </div>
  );
}
