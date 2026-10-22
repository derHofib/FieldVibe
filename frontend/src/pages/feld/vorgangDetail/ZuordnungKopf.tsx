import { Suspense, lazy } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../context/AuthContext";
import type { Adresse, Anlage, Kunde, Standort, Vorgang } from "../../../types";
import { adresseAlsZeile, leereAdresse } from "./helfer";
import type { UebersichtDaten } from "./useVorgangUebersicht";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und wuerde
// sonst in jedem Bundle landen, auch fuer Nutzer, die nie eine Karte sehen
// (und den PWA-Precache-Limit von 2 MiB sprengen).
const MapboxMap = lazy(() => import("../../../components/MapboxMap").then((m) => ({ default: m.MapboxMap })));

interface ZuordnungKopfProps {
  anlage: Anlage | undefined;
  anzeigeAdresse: Adresse | null;
  kartenKoordinaten: { lng: number; lat: number } | null;
  kunde: Kunde | undefined;
  standort: Standort | undefined;
  vorgang: Vorgang;
  uebersichtDaten: UebersichtDaten;
}

/** Titel, Zuordnung (Kunde/Anlage/Standort), weitere Anlagen und Adresse samt Karte. */
export function ZuordnungKopf({
  anlage, anzeigeAdresse, kartenKoordinaten, kunde, standort, vorgang, uebersichtDaten,
}: ZuordnungKopfProps) {
  const {
    adresseError, adresseForm, adresseMutation, alleKunden, anlageEntfernenMutation,
    anlageHinzufuegenMutation, anlagenFuerEditKunde, anlagenFuerVorgangKunde,
    bereitsZugeordneteAnlageIds, editAnlageId, editKundeId, editingAdresse, editingZuordnung,
    neueAnlageId, parentVorgang, setAdresseError, setAdresseForm, setEditAnlageId, setEditKundeId,
    setEditingAdresse, setEditingZuordnung, setNeueAnlageId, setShowAnlageHinzufuegen,
    setZuordnungError, showAnlageHinzufuegen, weitereAnlagen, zuordnungError, zuordnungMutation,
  } = uebersichtDaten;
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  return (
    <>
      <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
      <h1 className="font-heading text-lg font-semibold uppercase tracking-wide text-label">{vorgang.titel}</h1>
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
              className="text-tint underline-offset-2 hover:underline"
            >
              {kunde.name}
            </button>
          )}
          {anlage && (
            <>
              <span className="text-label2">·</span>
              <button
                onClick={() => navigate(`/anlagen/${anlage.id}`)}
                className="text-tint underline-offset-2 hover:underline"
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
            className="btn-touch text-xs font-medium text-tint"
          >
            Bearbeiten
          </button>
        )}
      </div>

      {editingZuordnung && (
        <div className="mt-2 space-y-2 border border-sepstrong p-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Kunde</label>
            <select
              value={editKundeId}
              onChange={(e) => {
                setEditKundeId(e.target.value);
                setEditAnlageId("");
              }}
              className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            >
              {alleKunden?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.kundennummer})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Anlage (optional)
            </label>
            <select
              value={editAnlageId}
              onChange={(e) => setEditAnlageId(e.target.value)}
              className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            >
              <option value="">Keine Anlage</option>
              {anlagenFuerEditKunde?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
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
              className="btn-touch text-xs font-medium text-tint"
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
                className="btn-touch text-xs font-medium text-tint"
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
              <select
                value={neueAnlageId}
                onChange={(e) => setNeueAnlageId(e.target.value)}
                className="btn-touch flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                <option value="">Anlage wählen…</option>
                {(anlagenFuerVorgangKunde ?? [])
                  .filter((a) => !bereitsZugeordneteAnlageIds.has(a.id))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.bezeichnung}
                    </option>
                  ))}
              </select>
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

    </>
  );
}
