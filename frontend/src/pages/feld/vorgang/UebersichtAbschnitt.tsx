import type { useBestaetigung } from "../../../components/ConfirmDialog";
import type { Adresse, Anlage, CurrentUser, Kunde, Leistungstyp, MandantEinstellungen, Standort, Vorgang, VorgangStatus } from "../../../types";
import { LEISTUNGSTYPEN, PRIORITAET_OPTIONEN, STATUS_LABEL, VORGANG_STATUS_GESCHLOSSEN, adresseAlsZeile, leereAdresse } from "./konstanten";
import { VorgangStatusAktionen } from "./VorgangStatusAktionen";
import type { UseMutationResult } from "@tanstack/react-query";
import { UserCheck } from "lucide-react";
import { Suspense, lazy, type Dispatch, type SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";
import { Select } from "../../../components/apple/Select";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und wuerde
// sonst in jedem Bundle landen, auch fuer Nutzer, die nie eine Karte sehen
// (und den PWA-Precache-Limit von 2 MiB sprengen).
const MapboxMap = lazy(() => import("../../../components/MapboxMap").then((m) => ({ default: m.MapboxMap })));

export function UebersichtAbschnitt({
  istAktiverTab,
  tabPanelProps,
  vorgang,
  parentVorgang,
  navigate,
  kunde,
  anlage,
  editingZuordnung,
  setEditKundeId,
  setEditAnlageId,
  setZuordnungError,
  setEditingZuordnung,
  editKundeId,
  alleKunden,
  editAnlageId,
  anlagenFuerEditKunde,
  zuordnungError,
  zuordnungMutation,
  kannDisponieren,
  editingAdresse,
  setAdresseForm,
  setAdresseError,
  setEditingAdresse,
  anzeigeAdresse,
  standort,
  kartenKoordinaten,
  adresseForm,
  adresseError,
  adresseMutation,
  weitereAnlagen,
  showAnlageHinzufuegen,
  setShowAnlageHinzufuegen,
  anlageEntfernenMutation,
  neueAnlageId,
  setNeueAnlageId,
  anlagenFuerVorgangKunde,
  bereitsZugeordneteAnlageIds,
  anlageHinzufuegenMutation,
  statusMutation,
  setWiedervorlageTage,
  setShowWartetKundeDialog,
  prioritaetMutation,
  setFolgeAuftragLeistungstyp,
  setShowFolgeAuftragDialog,
  currentUser,
  bestaetigen,
  uebernehmenMutation,
  uebernehmenKlebt = false,
  showWartetKundeDialog,
  mandantEinstellungen,
  wiedervorlageTage,
  showFolgeAuftragDialog,
  folgeAuftragLeistungstyp,
  folgeAuftragMutation,
  folgeVorgangId,
  folgeAuftraege,
}: {
  istAktiverTab: (ziel: string) => boolean;
  tabPanelProps: (ziel: string) => { role: "tabpanel"; "aria-labelledby": string; } | { role?: undefined; "aria-labelledby"?: undefined; };
  vorgang: Vorgang;
  parentVorgang: Vorgang | undefined;
  navigate: NavigateFunction;
  kunde: Kunde | undefined;
  anlage: Anlage | undefined;
  editingZuordnung: boolean;
  setEditKundeId: Dispatch<SetStateAction<string>>;
  setEditAnlageId: Dispatch<SetStateAction<string>>;
  setZuordnungError: Dispatch<SetStateAction<string | null>>;
  setEditingZuordnung: Dispatch<SetStateAction<boolean>>;
  editKundeId: string;
  alleKunden: Kunde[] | undefined;
  editAnlageId: string;
  anlagenFuerEditKunde: Anlage[] | undefined;
  zuordnungError: string | null;
  zuordnungMutation: UseMutationResult<Vorgang, Error, void, unknown>;
  kannDisponieren: boolean;
  editingAdresse: boolean;
  setAdresseForm: Dispatch<SetStateAction<{ strasse: string; plz: string; ort: string; }>>;
  setAdresseError: Dispatch<SetStateAction<string | null>>;
  setEditingAdresse: Dispatch<SetStateAction<boolean>>;
  anzeigeAdresse: Adresse | null;
  standort: Standort | undefined;
  kartenKoordinaten: { lng: number; lat: number; } | null;
  adresseForm: { strasse: string; plz: string; ort: string; };
  adresseError: string | null;
  adresseMutation: UseMutationResult<Vorgang, Error, void, unknown>;
  weitereAnlagen: Anlage[] | undefined;
  showAnlageHinzufuegen: boolean;
  setShowAnlageHinzufuegen: Dispatch<SetStateAction<boolean>>;
  anlageEntfernenMutation: UseMutationResult<void, unknown, string, unknown>;
  neueAnlageId: string;
  setNeueAnlageId: Dispatch<SetStateAction<string>>;
  anlagenFuerVorgangKunde: Anlage[] | undefined;
  bereitsZugeordneteAnlageIds: Set<string>;
  anlageHinzufuegenMutation: UseMutationResult<Anlage[], unknown, string, unknown>;
  statusMutation: UseMutationResult<Vorgang | null, unknown, { status: VorgangStatus; wiedervorlageTage?: number | undefined; }, unknown>;
  setWiedervorlageTage: Dispatch<SetStateAction<string>>;
  setShowWartetKundeDialog: Dispatch<SetStateAction<boolean>>;
  prioritaetMutation: UseMutationResult<Vorgang, unknown, number, unknown>;
  setFolgeAuftragLeistungstyp: Dispatch<SetStateAction<Leistungstyp>>;
  setShowFolgeAuftragDialog: Dispatch<SetStateAction<boolean>>;
  currentUser: CurrentUser | undefined;
  bestaetigen: ReturnType<typeof useBestaetigung>;
  uebernehmenMutation: UseMutationResult<Vorgang, unknown, void, unknown>;
  /** Klebende Leiste der Detailseite bietet "Vorgang übernehmen" schon an -- Karten-Button entfällt dann. */
  uebernehmenKlebt?: boolean;
  showWartetKundeDialog: boolean;
  mandantEinstellungen: MandantEinstellungen | undefined;
  wiedervorlageTage: string;
  showFolgeAuftragDialog: boolean;
  folgeAuftragLeistungstyp: Leistungstyp;
  folgeAuftragMutation: UseMutationResult<Vorgang, unknown, Leistungstyp, unknown>;
  folgeVorgangId: string | null;
  folgeAuftraege: Vorgang[] | undefined;
}) {
  return (
    <div
      id="abschnitt-uebersicht"
      className={`scroll-mt-4 grid gap-4 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
      {...tabPanelProps("abschnitt-uebersicht")}
    >
    <div className="card-ap p-4">
      <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
      <h1 className="font-heading text-lg font-semibold text-label">{vorgang.titel}</h1>
      {parentVorgang && (
        <button
          onClick={() => navigate(`/vorgaenge/${parentVorgang.id}`)}
          className="mt-0.5 block text-xs text-label2 underline-offset-2 hover:underline"
        >
          Entstanden aus Vorgang {parentVorgang.vorgangsnummer}
        </button>
      )}

      <div className="mt-1 flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
          {kunde && (
            <button
              onClick={() => navigate(`/kunden/${kunde.id}`)}
              className="text-tint-text underline-offset-2 hover:underline"
            >
              {kunde.name}
            </button>
          )}
          {anlage && (
            <>
              <span className="text-label2">·</span>
              <button
                onClick={() => navigate(`/anlagen/${anlage.id}`)}
                className="text-tint-text underline-offset-2 hover:underline"
              >
                {anlage.bezeichnung}
              </button>
            </>
          )}
        </div>
        {!editingZuordnung && (
          <button
            onClick={() => {
              setEditKundeId(vorgang.kunde_id);
              setEditAnlageId(vorgang.anlage_id ?? "");
              setZuordnungError(null);
              setEditingZuordnung(true);
            }}
            className="btn-touch text-xs font-medium text-tint-text"
          >
            Bearbeiten
          </button>
        )}
      </div>

      {editingZuordnung && (
        <div className="mt-2 space-y-2 border border-sepstrong p-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Kunde</label>
            <Select
              value={editKundeId}
              onChange={(e) => {
                setEditKundeId(e.target.value);
                setEditAnlageId("");
              }}
            >
              {alleKunden?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.kundennummer})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Anlage (optional)
            </label>
            <Select
              value={editAnlageId}
              onChange={(e) => setEditAnlageId(e.target.value)}
            >
              <option value="">Keine Anlage</option>
              {anlagenFuerEditKunde?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </Select>
          </div>
          {zuordnungError && <p className="text-xs text-st-fehlt">{zuordnungError}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => zuordnungMutation.mutate()}
              disabled={!editKundeId || zuordnungMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
            >
              Speichern
            </button>
            <button
              onClick={() => {
                setEditingZuordnung(false);
                setZuordnungError(null);
              }}
              className="btn-touch flex-1 btn-ap py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div className="mt-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-label2">Adresse</span>
          {kannDisponieren && !editingAdresse && (
            <button
              onClick={() => {
                setAdresseForm(leereAdresse(vorgang.adresse));
                setAdresseError(null);
                setEditingAdresse(true);
              }}
              className="btn-touch text-xs font-medium text-tint-text"
            >
              Bearbeiten
            </button>
          )}
        </div>
        {!editingAdresse &&
          (adresseAlsZeile(anzeigeAdresse) ? (
            <>
              <p className="mt-1 text-sm text-label">
                {adresseAlsZeile(anzeigeAdresse)}
                {!vorgang.adresse && (standort || anlage) && (
                  <span className="ml-1 text-xs text-label2">
                    ({standort ? "Standort" : "Anlage"})
                  </span>
                )}
              </p>
              {kartenKoordinaten ? (
                <Suspense
                  fallback={<div className="mt-2 h-40 w-full animate-pulse rounded-lg bg-fill" />}
                >
                  <MapboxMap
                    lng={kartenKoordinaten.lng}
                    lat={kartenKoordinaten.lat}
                    className="mt-2 h-40 w-full rounded-lg"
                  />
                </Suspense>
              ) : (
                <div className="mt-2 flex h-40 w-full items-center justify-center border border-dashed border-sepstrong text-center text-xs text-label2">
                  Keine Kartenposition verfügbar
                </div>
              )}
            </>
          ) : (
            <p className="mt-1 text-sm text-label2">Keine Adresse hinterlegt.</p>
          ))}
        {editingAdresse && (
          <div className="mt-2 space-y-2 border border-sepstrong p-3">
            <input
              value={adresseForm.strasse}
              onChange={(e) => setAdresseForm({ ...adresseForm, strasse: e.target.value })}
              placeholder="Straße + Hausnr."
              className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                value={adresseForm.plz}
                onChange={(e) => setAdresseForm({ ...adresseForm, plz: e.target.value })}
                placeholder="PLZ"
                className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                value={adresseForm.ort}
                onChange={(e) => setAdresseForm({ ...adresseForm, ort: e.target.value })}
                placeholder="Ort"
                className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            {adresseError && <p className="text-xs text-st-fehlt">{adresseError}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => adresseMutation.mutate()}
                disabled={adresseMutation.isPending}
                className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
              >
                Speichern
              </button>
              <button
                onClick={() => {
                  setEditingAdresse(false);
                  setAdresseError(null);
                }}
                className="btn-touch flex-1 btn-ap py-1.5 text-sm"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}
      </div>

      {((weitereAnlagen && weitereAnlagen.length > 0) || kannDisponieren) && (
        <div className="mt-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-label2">Weitere Anlagen</span>
            {kannDisponieren && !showAnlageHinzufuegen && (
              <button
                onClick={() => setShowAnlageHinzufuegen(true)}
                className="btn-touch text-xs font-medium text-tint-text"
              >
                + Hinzufügen
              </button>
            )}
          </div>
          {(weitereAnlagen ?? []).length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {weitereAnlagen!.map((a) => (
                <span
                  key={a.id}
                  className="flex items-center gap-1 border border-sep px-2 py-1 text-xs text-label"
                >
                  <button
                    onClick={() => navigate(`/anlagen/${a.id}`)}
                    className="underline-offset-2 hover:underline"
                  >
                    {a.bezeichnung}
                  </button>
                  {kannDisponieren && (
                    <button
                      onClick={() => anlageEntfernenMutation.mutate(a.id)}
                      disabled={anlageEntfernenMutation.isPending}
                      className="relative text-label2 before:absolute before:-inset-2.5 hover:text-st-fehlt"
                      aria-label={`${a.bezeichnung} entfernen`}
                    >
                      ✕
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          {showAnlageHinzufuegen && (
            <div className="mt-2 flex gap-2">
              <Select
                className="flex-1"
                value={neueAnlageId}
                onChange={(e) => setNeueAnlageId(e.target.value)}
                groesse="kompakt"
              >
                <option value="">Anlage wählen…</option>
                {(anlagenFuerVorgangKunde ?? [])
                  .filter((a) => !bereitsZugeordneteAnlageIds.has(a.id))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.bezeichnung}
                    </option>
                  ))}
              </Select>
              <button
                onClick={() => anlageHinzufuegenMutation.mutate(neueAnlageId)}
                disabled={!neueAnlageId || anlageHinzufuegenMutation.isPending}
                className="btn-touch btn-ap-primary px-3 py-1.5 text-sm"
              >
                OK
              </button>
              <button
                onClick={() => {
                  setShowAnlageHinzufuegen(false);
                  setNeueAnlageId("");
                }}
                className="btn-touch btn-ap px-3 py-1.5 text-sm"
              >
                Abbrechen
              </button>
            </div>
          )}
        </div>
      )}

      {vorgang.beschreibung && (
        <p className="mt-2 text-sm text-label">{vorgang.beschreibung}</p>
      )}

      <VorgangStatusAktionen
        status={vorgang.status}
        darfAendern={kannDisponieren}
        pending={statusMutation.isPending}
        onWaehle={(status) => {
          if (status === "wartet_kunde") {
            setWiedervorlageTage("");
            setShowWartetKundeDialog(true);
            return;
          }
          statusMutation.mutate({ status });
        }}
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {vorgang.dauerauftrag_id ? (
          <span
            title="Wird beim Dauerauftrag automatisch anhand der Fälligkeit berechnet"
            className="rounded-[var(--radius-ap-pill)] bg-fill px-2 py-1 text-xs text-label"
          >
            Priorität {vorgang.prioritaet} (automatisch)
          </span>
        ) : (
          <label className="flex items-center gap-1 text-sm text-label2">
            Priorität
            <Select
              className="w-auto"
              value={vorgang.prioritaet}
              disabled={VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) || prioritaetMutation.isPending}
              onChange={(e) => prioritaetMutation.mutate(Number(e.target.value))}
              groesse="kompakt"
            >
              {PRIORITAET_OPTIONEN.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </label>
        )}
        <button
          onClick={() => {
            setFolgeAuftragLeistungstyp("stoerung");
            setShowFolgeAuftragDialog(true);
          }}
          className="btn-touch btn-ap px-3 py-1 text-xs"
        >
          + Folge-Vorgang
        </button>
      </div>

      {!VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-label2">
            {vorgang.zugewiesener_name ? (
              <>
                Zugewiesen an: <span className="font-medium text-label">{vorgang.zugewiesener_name}</span>
              </>
            ) : (
              "Nicht zugewiesen"
            )}
          </span>
          {currentUser?.darf_vorgaenge_selbst_uebernehmen && !uebernehmenKlebt && (
            <button
              onClick={async () => {
                if (
                  vorgang.zugewiesener_user_id &&
                  vorgang.zugewiesener_user_id !== currentUser.id &&
                  !(await bestaetigen({ titel: `Dieser Vorgang ist bereits "${vorgang.zugewiesener_name}" zugewiesen. Trotzdem an mich übernehmen?`, bestaetigenLabel: "Übernehmen", destruktiv: false }))
                ) {
                  return;
                }
                uebernehmenMutation.mutate();
              }}
              disabled={uebernehmenMutation.isPending || vorgang.zugewiesener_user_id === currentUser.id}
              className="btn-touch btn-ap-primary flex items-center gap-1 px-3 py-1.5 text-xs disabled:cursor-not-allowed"
            >
              <UserCheck size={13} strokeWidth={2} />
              {vorgang.zugewiesener_user_id === currentUser.id ? "Von mir übernommen" : "Vorgang übernehmen"}
            </button>
          )}
        </div>
      )}

      {showWartetKundeDialog && (
        <div className="mt-2 space-y-2 border border-sepstrong p-2">
          <p className="text-sm text-label">
            Wartet auf Kunde: Nach wie vielen Tagen soll FieldVibe dich erinnern, nachzufragen?
          </p>
          <input
            type="number"
            min={1}
            placeholder={
              mandantEinstellungen
                ? mandantEinstellungen.effektive_wiedervorlage_standard_tage.toString()
                : "14"
            }
            value={wiedervorlageTage}
            onChange={(e) => setWiedervorlageTage(e.target.value)}
            className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                statusMutation.mutate({
                  status: "wartet_kunde",
                  wiedervorlageTage: wiedervorlageTage ? Number(wiedervorlageTage) : undefined,
                });
                setShowWartetKundeDialog(false);
              }}
              disabled={statusMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
            >
              Übernehmen
            </button>
            <button
              onClick={() => setShowWartetKundeDialog(false)}
              className="btn-touch flex-1 btn-ap py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showFolgeAuftragDialog && (
        <div className="mt-2 space-y-2 border border-sepstrong p-2">
          <p className="text-sm text-label">
            Folge-Vorgang anlegen: übernimmt Kunde/Anlage/Standort sowie offene Angebots-
            Materialpositionen dieses Vorgangs. Dieser Vorgang bleibt dabei unverändert.
          </p>
          <Select
            value={folgeAuftragLeistungstyp}
            onChange={(e) => setFolgeAuftragLeistungstyp(e.target.value as Leistungstyp)}
          >
            {LEISTUNGSTYPEN.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </Select>
          <div className="flex gap-2">
            <button
              onClick={() => {
                folgeAuftragMutation.mutate(folgeAuftragLeistungstyp);
                setShowFolgeAuftragDialog(false);
              }}
              disabled={folgeAuftragMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
            >
              Anlegen
            </button>
            <button
              onClick={() => setShowFolgeAuftragDialog(false)}
              className="btn-touch flex-1 btn-ap py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {folgeVorgangId && (
        <div className="mt-2 flex items-center justify-between rounded-md bg-st-erledigt-bg px-3 py-2 text-sm text-st-erledigt">
          <span>Folge-Vorgang wurde angelegt.</span>
          <button
            onClick={() => navigate(`/vorgaenge/${folgeVorgangId}`)}
            className="btn-touch font-medium underline"
          >
            Jetzt ansehen
          </button>
        </div>
      )}

      {folgeAuftraege && folgeAuftraege.length > 0 && (
        <div className="mt-2 space-y-1">
          <span className="text-xs font-medium text-label2">Folge-Vorgänge:</span>
          {folgeAuftraege.map((fa) => (
            <button
              key={fa.id}
              onClick={() => navigate(`/vorgaenge/${fa.id}`)}
              className="btn-touch block w-full border border-sep px-2 py-1.5 text-left text-sm text-label hover:bg-fill"
            >
              {fa.vorgangsnummer} · {fa.titel} · {STATUS_LABEL[fa.status]}
            </button>
          ))}
        </div>
      )}
    </div>

    </div>
  );
}
