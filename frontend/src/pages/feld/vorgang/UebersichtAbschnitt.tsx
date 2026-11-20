import type { UseMutationResult } from "@tanstack/react-query";
import { Building2, GitBranch, MapPin } from "lucide-react";
import { Suspense, lazy, type Dispatch, type ReactNode, type SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";

import { Select } from "../../../components/apple/Select";
import { VorgangStatusPille } from "../../../components/VorgangStatusPille";
import type { Adresse, Anlage, ProjektAufgabe, Standort, Vorgang } from "../../../types";
import { ABRECHNUNGSART_LABEL, LEISTUNGSTYP_LABEL, adresseAlsZeile, leereAdresse } from "./konstanten";
import { ABSCHNITT_AKTION, Abschnitt } from "./Abschnitt";
import { useZweispaltig } from "./useZweispaltig";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und wuerde
// sonst in jedem Bundle landen, auch fuer Nutzer, die nie eine Karte sehen
// (und den PWA-Precache-Limit von 2 MiB sprengen).
const MapboxMap = lazy(() => import("../../../components/MapboxMap").then((m) => ({ default: m.MapboxMap })));

const ZEILE_ICON = "flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-ap-md)] bg-fill text-label2";

export function UebersichtAbschnitt({
  istAktiverTab,
  tabPanelProps,
  zweispaltigMoeglich,
  vorgang,
  parentVorgang,
  navigate,
  anlage,
  standort,
  kannDisponieren,
  editingAdresse,
  setAdresseForm,
  setAdresseError,
  setEditingAdresse,
  anzeigeAdresse,
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
  onFolgeVorgang,
  folgeAuftraege,
  verknuepfteAufgaben,
  erstelltVonName,
  formulare,
  partner,
  vorOrt,
  vorOrtKontakte,
  einheitZeile,
}: {
  istAktiverTab: (ziel: string) => boolean;
  tabPanelProps: (ziel: string) => { role: "tabpanel"; "aria-labelledby": string } | { role?: undefined; "aria-labelledby"?: undefined };
  /** Nur Office-Panel: zwei Spalten, sobald das Panel breit genug ist (nicht neben der festen Verlauf-Spalte). */
  zweispaltigMoeglich: boolean;
  vorgang: Vorgang;
  parentVorgang: Vorgang | undefined;
  navigate: NavigateFunction;
  anlage: Anlage | undefined;
  standort: Standort | undefined;
  kannDisponieren: boolean;
  editingAdresse: boolean;
  setAdresseForm: Dispatch<SetStateAction<{ strasse: string; plz: string; ort: string }>>;
  setAdresseError: Dispatch<SetStateAction<string | null>>;
  setEditingAdresse: Dispatch<SetStateAction<boolean>>;
  anzeigeAdresse: Adresse | null;
  kartenKoordinaten: { lng: number; lat: number } | null;
  adresseForm: { strasse: string; plz: string; ort: string };
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
  onFolgeVorgang: () => void;
  folgeAuftraege: Vorgang[] | undefined;
  verknuepfteAufgaben: ProjektAufgabe[] | undefined;
  erstelltVonName: string | undefined;
  /** FormularAbschnitt (rendert sich selbst nur, wenn es Formulare gibt). */
  formulare: ReactNode;
  /** PartnerAbschnitt (nur mit Recht/Modul). */
  partner: ReactNode;
  /** Gruppe "Auftraggeber" (VorgangAuftraggeber), steht ganz oben. */
  vorOrt: ReactNode;
  /** Gruppe "Vor Ort" mit den Kontakten, folgt unmittelbar auf den Einsatzort. */
  vorOrtKontakte: ReactNode;
  /** Einheit unter der Adresse im Einsatzort. */
  einheitZeile: ReactNode;
}) {
  const { wurzel, zweispaltig } = useZweispaltig(zweispaltigMoeglich);

  const adresseText = adresseAlsZeile(anzeigeAdresse);
  const hatVerknuepft =
    !!parentVorgang || (folgeAuftraege?.length ?? 0) > 0 || (verknuepfteAufgaben?.length ?? 0) > 0;

  const beschreibung = (
    <Abschnitt titel="Beschreibung">
      {vorgang.beschreibung ? (
        <p className="text-fliess whitespace-pre-line text-label">{vorgang.beschreibung}</p>
      ) : (
        <p className="text-fliess text-label2">Keine Beschreibung.</p>
      )}
    </Abschnitt>
  );

  const einsatzort = (
    <Abschnitt
      titel="Einsatzort"
      aktion={
        kannDisponieren && !editingAdresse ? (
          <button
            onClick={() => {
              setAdresseForm(leereAdresse(vorgang.adresse));
              setAdresseError(null);
              setEditingAdresse(true);
            }}
            className={ABSCHNITT_AKTION}
          >
            Bearbeiten
          </button>
        ) : undefined
      }
    >
      {!editingAdresse && (
        <div className="divide-y-[0.5px] divide-sep">
          <div className="flex items-start gap-3 pb-2">
            <span className={ZEILE_ICON}>
              <MapPin size={15} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              {adresseText ? (
                <p className="text-fliess text-label">
                  {adresseText}
                  {!vorgang.adresse && (standort || anlage) && (
                    <span className="ml-1 text-meta text-label2">({standort ? "Standort" : "Anlage"})</span>
                  )}
                </p>
              ) : (
                <p className="pt-0.5 text-fliess text-label2">Keine Adresse hinterlegt.</p>
              )}
              {einheitZeile}
            </div>
          </div>
          {[
            { key: "haupt", anlage: anlage, weitere: false },
            ...(weitereAnlagen ?? []).map((a) => ({ key: a.id, anlage: a, weitere: true })),
          ].map((zeile, idx, alle) => {
            const letzte = idx === alle.length - 1;
            const plusAnlage =
              letzte && kannDisponieren && !showAnlageHinzufuegen ? (
                <button onClick={() => setShowAnlageHinzufuegen(true)} className={`${ABSCHNITT_AKTION} ml-auto`}>
                  + Anlage
                </button>
              ) : null;
            return (
              <div key={zeile.key} className="flex items-center gap-3 py-2 last:pb-0">
                <span className={ZEILE_ICON}>
                  <Building2 size={15} strokeWidth={1.5} aria-hidden="true" />
                </span>
                {zeile.anlage ? (
                  <button
                    onClick={() => navigate(`/anlagen/${zeile.anlage!.id}`)}
                    className="min-w-0 truncate text-left text-fliess text-tint-text underline-offset-2 hover:underline"
                  >
                    {zeile.anlage.bezeichnung}
                  </button>
                ) : (
                  <span className="text-fliess text-label2">Keine Anlage</span>
                )}
                {zeile.weitere && kannDisponieren && (
                  <button
                    onClick={() => anlageEntfernenMutation.mutate(zeile.anlage!.id)}
                    disabled={anlageEntfernenMutation.isPending}
                    className="relative text-label2 before:absolute before:-inset-2.5 hover:text-st-fehlt"
                    aria-label={`${zeile.anlage!.bezeichnung} entfernen`}
                  >
                    ✕
                  </button>
                )}
                {plusAnlage}
              </div>
            );
          })}
        </div>
      )}

      {!editingAdresse && adresseText && (
        kartenKoordinaten ? (
          <Suspense fallback={<div className="mt-2 h-40 w-full animate-pulse rounded-lg bg-fill" />}>
            <MapboxMap lng={kartenKoordinaten.lng} lat={kartenKoordinaten.lat} className="mt-2 h-40 w-full rounded-lg" />
          </Suspense>
        ) : (
          <div className="mt-2 flex h-40 w-full items-center justify-center rounded-[var(--radius-ap-md)] border border-dashed border-sepstrong text-center text-sekundaer text-label2">
            Keine Kartenposition verfügbar
          </div>
        )
      )}

      {editingAdresse && (
        <div className="space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
          <input
            value={adresseForm.strasse}
            onChange={(e) => setAdresseForm({ ...adresseForm, strasse: e.target.value })}
            placeholder="Straße + Hausnr."
            className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              value={adresseForm.plz}
              onChange={(e) => setAdresseForm({ ...adresseForm, plz: e.target.value })}
              placeholder="PLZ"
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <input
              value={adresseForm.ort}
              onChange={(e) => setAdresseForm({ ...adresseForm, ort: e.target.value })}
              placeholder="Ort"
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          {adresseError && <p className="text-sekundaer text-st-fehlt">{adresseError}</p>}
          <div className="flex gap-2">
            <button onClick={() => adresseMutation.mutate()} disabled={adresseMutation.isPending} className="btn-touch btn-ap-primary flex-1 py-1.5 text-sekundaer">
              Speichern
            </button>
            <button
              onClick={() => {
                setEditingAdresse(false);
                setAdresseError(null);
              }}
              className="btn-touch flex-1 btn-ap py-1.5 text-sekundaer"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showAnlageHinzufuegen && (
        <div className="mt-2 flex gap-2">
          <Select className="flex-1" value={neueAnlageId} onChange={(e) => setNeueAnlageId(e.target.value)} groesse="kompakt">
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
            className="btn-touch btn-ap-primary px-3 py-1.5 text-sekundaer"
          >
            OK
          </button>
          <button
            onClick={() => {
              setShowAnlageHinzufuegen(false);
              setNeueAnlageId("");
            }}
            className="btn-touch btn-ap px-3 py-1.5 text-sekundaer"
          >
            Abbrechen
          </button>
        </div>
      )}
    </Abschnitt>
  );

  const detailZeilen: [string, string | undefined][] = [
    ["Leistungstyp", LEISTUNGSTYP_LABEL[vorgang.leistungstyp]],
    ["Abrechnungsart", ABRECHNUNGSART_LABEL[vorgang.abrechnungsart]],
    ["Erstellt am", new Date(vorgang.created_at).toLocaleDateString("de-DE")],
    ["Erstellt von", erstelltVonName ?? (vorgang.erstellt_von_kundenportal_zugang_id ? "Kundenportal" : undefined)],
  ];
  const details = (
    <Abschnitt titel="Details">
      <dl className="space-y-1.5 text-fliess">
        {detailZeilen
          .filter(([, wert]) => wert)
          .map(([label, wert]) => (
            <div key={label} className="flex items-baseline justify-between gap-3">
              <dt className="text-label2">{label}</dt>
              <dd className="text-right font-medium text-label">{wert}</dd>
            </div>
          ))}
      </dl>
    </Abschnitt>
  );

  const verknuepft = hatVerknuepft ? (
    <Abschnitt
      titel="Verknüpft"
      aktion={
        <button onClick={onFolgeVorgang} className={ABSCHNITT_AKTION}>
          + Folge-Vorgang
        </button>
      }
    >
      <div className="space-y-1.5">
        {parentVorgang && (
          <div className="flex items-center gap-3 text-fliess">
            <span className={ZEILE_ICON}>
              <GitBranch size={15} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <span className="text-label2">Entstanden aus</span>
            <button onClick={() => navigate(`/vorgaenge/${parentVorgang.id}`)} className="min-w-0 truncate text-left text-tint-text underline-offset-2 hover:underline">
              {parentVorgang.vorgangsnummer} · {parentVorgang.titel}
            </button>
          </div>
        )}
        {(folgeAuftraege ?? []).map((fa) => (
          <button
            key={fa.id}
            onClick={() => navigate(`/vorgaenge/${fa.id}`)}
            className="flex w-full items-center gap-3 text-left text-fliess hover:bg-fill"
          >
            <span className={ZEILE_ICON}>
              <GitBranch size={15} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <span className="text-label2">Folge-Vorgang</span>
            <span className="min-w-0 flex-1 truncate text-tint-text">
              {fa.vorgangsnummer} · {fa.titel}
            </span>
            <VorgangStatusPille status={fa.status} />
          </button>
        ))}
        {/* Rein anzeigend: Bearbeitung nur ueber das Projekte-Kanban in der
            Office-Oberflaeche, kein Statusabgleich zurueck zum Vorgang. */}
        {(verknuepfteAufgaben ?? []).map((a) => (
          <div key={a.id} className="rounded-[var(--radius-ap-md)] bg-fill p-2 text-fliess">
            <div className="flex items-start justify-between gap-2">
              <p className="text-label">{a.titel}</p>
              <span className="shrink-0 rounded-[var(--radius-ap-pill)] bg-fill2 px-2 py-0.5 text-meta font-medium text-label">{a.prioritaet}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-sekundaer text-label2">
              <span>
                {a.checkliste.length > 0
                  ? `${a.checkliste.filter((p) => p.erledigt).length}/${a.checkliste.length} erledigt`
                  : a.zugewiesener_name || "Nicht zugewiesen"}
              </span>
              {a.faelligkeit_am && <span>fällig {a.faelligkeit_am}</span>}
            </div>
          </div>
        ))}
      </div>
    </Abschnitt>
  ) : null;

  return (
    <div
      id="abschnitt-uebersicht"
      ref={wurzel}
      className={`scroll-mt-4 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
      {...tabPanelProps("abschnitt-uebersicht")}
    >
      {zweispaltig ? (
        <div className="grid grid-cols-[minmax(0,1fr)_320px] items-start gap-x-4">
          <div className="min-w-0">
            {vorOrt}
            {beschreibung}
            {formulare}
            {verknuepft}
            {partner}
          </div>
          <div className="min-w-0 border-l-[0.5px] border-sep pl-4">
            {einsatzort}
            {vorOrtKontakte}
            {details}
          </div>
        </div>
      ) : (
        <div className="space-y-4 in-[.office-panel]:space-y-0">
          {vorOrt}
          {beschreibung}
          {einsatzort}
          {vorOrtKontakte}
          {formulare}
          {details}
          {verknuepft}
          {partner}
        </div>
      )}
    </div>
  );
}
