import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { MandantModul, MandantStatus } from "../types";

const STATUS_LABEL: Record<MandantStatus, string> = {
  aktiv: "Aktiv",
  pausiert: "Pausiert",
  gekuendigt: "Gekündigt",
};

// Ein Wechsel in einen dieser Status sperrt den Mandanten fuer seine Nutzer
// (siehe require_active_mandant in app/api/deps.py) -- verdient eine
// Rueckfrage, bevor das versehentlich per Dropdown ausgeloest wird.
const STATUS_BESTAETIGUNG: Record<MandantStatus, string | null> = {
  aktiv: null,
  pausiert: "Mandant wirklich pausieren? Alle Nutzer dieses Mandanten werden sofort ausgesperrt.",
  gekuendigt: "Mandant wirklich kündigen? Alle Nutzer dieses Mandanten werden sofort ausgesperrt.",
};

const MODUL_LABEL: Record<MandantModul, string> = {
  kundenverwaltung: "Kundenverwaltung (Ansprechpartner, Adresse, Löschen)",
  dispo: "Dispo/Termine",
  material: "Materialwirtschaft (Lager/Bestand)",
  pruefzyklen: "Prüfzyklen & Prüfmittel",
  abrechnung: "Mängel/Angebote/Rechnungen",
  kundenportal: "Kundenportal",
  dauerauftrag: "Dauer-Aufträge",
  zeiterfassung: "Zeiterfassung (eigene Arbeitszeit erfassen & einsehen)",
  statistik: "Auswertung & Export (Kennzahlen, Zeiterfassung-Auswertung, CSV/PDF)",
  fahrzeuge: "Fahrzeug-Zuweisung & Inventur",
  highlights: "Highlights (Story-Feature)",
  karten: "Kartenansicht (Mapbox)",
  nachunternehmer: "Partner-/Nachunternehmer-Verwaltung",
  postfach: "Postfach (persönlicher E-Mail-Client)",
};
const ALLE_MODULE = Object.keys(MODUL_LABEL) as MandantModul[];

export function MandantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { startImpersonation, isImpersonating } = useAuth();

  const { data: mandant, isLoading } = useQuery({
    queryKey: ["mandanten", id],
    queryFn: () => mandantenApi.get(id!),
    // super_admin-only endpoint: siehe MandantenPage fuer den Impersonation-
    // Race, den dieses Disablen abfaengt.
    enabled: !!id && !isImpersonating,
  });

  const [name, setName] = useState("");
  const [branche, setBranche] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [gespeichertHinweis, setGespeichertHinweis] = useState(false);

  // Formularfelder erst nach dem Laden mit den echten Werten fuellen -- beim
  // ersten Render ist der Query noch nicht zurueck.
  useEffect(() => {
    if (mandant) {
      setName(mandant.name);
      setBranche(mandant.branche ?? "");
    }
  }, [mandant?.id]);

  const stammdatenMutation = useMutation({
    mutationFn: () => mandantenApi.update(id!, { name, branche: branche || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandanten"] });
      setFormError(null);
      setGespeichertHinweis(true);
      setTimeout(() => setGespeichertHinweis(false), 2000);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const statusMutation = useMutation({
    mutationFn: (status: MandantStatus) => mandantenApi.update(id!, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  const moduleMutation = useMutation({
    mutationFn: (deaktivierteModule: MandantModul[]) =>
      mandantenApi.update(id!, { deaktivierte_module: deaktivierteModule }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  function handleSaveStammdaten(e: FormEvent) {
    e.preventDefault();
    stammdatenMutation.mutate();
  }

  function handleStatusChange(status: MandantStatus) {
    const frage = STATUS_BESTAETIGUNG[status];
    if (frage && !window.confirm(frage)) return;
    statusMutation.mutate(status);
  }

  function toggleModul(modul: MandantModul) {
    if (!mandant) return;
    const aktuell = mandant.deaktivierte_module;
    const naechste = aktuell.includes(modul)
      ? aktuell.filter((m) => m !== modul)
      : [...aktuell, modul];
    moduleMutation.mutate(naechste);
  }

  if (isLoading) return <p className="text-label2">Lädt…</p>;
  if (!mandant) return <p className="text-label2">Mandant nicht gefunden.</p>;

  return (
    <div className="max-w-2xl space-y-8">
      <Link to="/mandanten" className="text-sm font-medium text-tint hover:underline">
        ← Zurück zu Mandanten
      </Link>

      <section>
        <h2 className="mb-4 text-lg font-bold text-label">Stammdaten</h2>
        <form onSubmit={handleSaveStammdaten} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">
              Slug (Subdomain)
            </label>
            <input
              disabled
              value={mandant.slug}
              title="Der Slug ist mit dem Kundenportal-Link verknuepft und kann nachtraeglich nicht geaendert werden."
              className="btn-touch w-full rounded-md border border-sep bg-slate-100 px-3 py-2 text-label2 dark:bg-stone-950"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Branche</label>
            <input
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={stammdatenMutation.isPending}
              className="btn-touch btn-ap-primary"
            >
              Speichern
            </button>
            {gespeichertHinweis && (
              <span className="text-sm text-st-erledigt ">✓ Gespeichert</span>
            )}
          </div>
          {formError && <p className="text-sm text-st-fehlt ">{formError}</p>}
        </form>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-label">Status</h2>
        <select
          value={mandant.status}
          disabled={statusMutation.isPending}
          onChange={(e) => handleStatusChange(e.target.value as MandantStatus)}
          className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
        >
          {Object.entries(STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <div className="mt-3">
          <button
            disabled={isImpersonating || mandant.status !== "aktiv"}
            onClick={() => startImpersonation(mandant.id)}
            className="btn-touch rounded-md bg-st-arbeit-dot px-3 py-2 text-xs font-semibold text-st-arbeit hover:bg-st-arbeit-dot disabled:opacity-40"
            title="Support-Zugriff: Login als Mandant"
          >
            Login als Mandant
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-label">Module</h2>
        <p className="mb-2 text-xs text-label2">
          "Aufträge" (Anlegen, Chat/Foto/Status, Zeit start/stopp) ist immer aktiv und hier nicht
          abwählbar.
        </p>
        <div className="space-y-1.5 rounded-md bg-fill p-3">
          {ALLE_MODULE.map((modul) => (
            <label key={modul} className="btn-touch flex items-center gap-2 text-sm text-label">
              <input
                type="checkbox"
                checked={!mandant.deaktivierte_module.includes(modul)}
                disabled={moduleMutation.isPending}
                onChange={() => toggleModul(modul)}
              />
              {MODUL_LABEL[modul]}
            </label>
          ))}
        </div>
      </section>

      <button
        onClick={() => navigate("/mandanten")}
        className="btn-touch text-sm font-medium text-label2 hover:underline "
      >
        ← Zurück zu Mandanten
      </button>
    </div>
  );
}
