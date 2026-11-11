import { type FormEvent, useEffect, useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { MandantModul, MandantStatus } from "../types";
import { FehlerZustand } from "../components/FehlerZustand";
import { useBestaetigung } from "../components/ConfirmDialog";
import { DetailSkeleton } from "../components/Skeleton";
import { Select } from "../components/apple/Select";

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
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { startImpersonation, isImpersonating } = useAuth();

  const { data: mandant, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["mandanten", id],
    queryFn: () => mandantenApi.get(id!),
    // super_admin-only endpoint: siehe MandantenPage fuer den Impersonation-
    // Race, den dieses Disablen abfaengt.
    enabled: !!id && !isImpersonating,
  });

  const [name, setName] = useState("");
  const [branche, setBranche] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [nameFehler, setNameFehler] = useState<string | null>(null);

  // Formularfelder erst nach dem Laden mit den echten Werten fuellen -- beim
  // ersten Render ist der Query noch nicht zurueck.
  useEffect(() => {
    if (mandant) {
      setName(mandant.name);
      setBranche(mandant.branche ?? "");
    }
  }, [mandant?.id]);

  const stammdatenMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => mandantenApi.update(id!, { name, branche: branche || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandanten"] });
      setFormError(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const statusMutation = useMutation({
    meta: { erfolg: "Status geändert" },
    mutationFn: (status: MandantStatus) => mandantenApi.update(id!, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  const moduleMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: (deaktivierteModule: MandantModul[]) =>
      mandantenApi.update(id!, { deaktivierte_module: deaktivierteModule }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandanten"] }),
  });

  function handleSaveStammdaten(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setNameFehler("Bitte einen Namen eingeben.");
      return;
    }
    setNameFehler(null);
    stammdatenMutation.mutate();
  }

  async function handleStatusChange(status: MandantStatus) {
    const frage = STATUS_BESTAETIGUNG[status];
    if (frage) {
      const [titel, text] = frage.split("? ");
      if (!(await bestaetigen({ titel: titel + "?", text, bestaetigenLabel: status === "pausiert" ? "Pausieren" : "Kündigen" }))) return;
    }
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

  if (ladeFehler && !mandant) return <FehlerZustand fehler={ladeFehler} was="Der Mandant" zurueck onErneut={() => void neuLaden()} className="py-6" />;
  if (isLoading) return <DetailSkeleton />;
  if (!mandant) return <p className="text-label2">Mandant nicht gefunden.</p>;

  return (
    <div className="max-w-2xl space-y-8">
      <Link to="/mandanten" className="text-fliess font-medium text-tint-text hover:underline">
        ← Zurück zu Mandanten
      </Link>

      <section>
        <h2 className="mb-4 text-zeile font-bold text-label">Stammdaten</h2>
        <form onSubmit={handleSaveStammdaten} className="space-y-3" noValidate>
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">
              Name <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input id={`${uid}-0`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={!!nameFehler}
              aria-describedby={nameFehler ? `${uid}-name-fehler` : undefined}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
            {nameFehler && (
              <p id={`${uid}-name-fehler`} role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                {nameFehler}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-fliess font-medium text-label">
              Slug (Subdomain)
            </label>
            <input id={`${uid}-1`}
              disabled
              value={mandant.slug}
              title="Der Slug ist mit dem Kundenportal-Link verknüpft und kann nachträglich nicht geändert werden."
              className="btn-touch w-full rounded-md border border-sep bg-slate-100 px-3 py-2 text-label2 dark:bg-stone-950"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-2`} className="mb-1 block text-fliess font-medium text-label">Branche</label>
            <input id={`${uid}-2`}
              value={branche}
              onChange={(e) => setBranche(e.target.value)}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
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
          </div>
          {formError && <p className="text-fliess text-st-fehlt ">{formError}</p>}
        </form>
      </section>

      <section>
        <h2 className="mb-4 text-zeile font-bold text-label">Status</h2>
        <Select
          className="w-auto"
          aria-label="Status des Mandanten"
          value={mandant.status}
          disabled={statusMutation.isPending}
          onChange={(e) => handleStatusChange(e.target.value as MandantStatus)}
        >
          {Object.entries(STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <div className="mt-3">
          <button
            disabled={isImpersonating || mandant.status !== "aktiv"}
            onClick={() => startImpersonation(mandant.id)}
            className="btn-touch rounded-md bg-st-arbeit-dot px-3 py-2 text-sekundaer font-semibold text-st-arbeit hover:bg-st-arbeit-dot disabled:opacity-40"
            title="Support-Zugriff: Login als Mandant"
          >
            Login als Mandant
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-zeile font-bold text-label">Module</h2>
        <p className="mb-2 text-meta text-label2">
          "Vorgänge" (Anlegen, Chat/Foto/Status, Zeit start/stopp) ist immer aktiv und hier nicht
          abwählbar.
        </p>
        <div className="space-y-1.5 rounded-md bg-fill p-3">
          {ALLE_MODULE.map((modul) => (
            <label key={modul} className="btn-touch flex items-center gap-2 text-sekundaer text-label">
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
        className="btn-touch text-sekundaer font-medium text-label2 hover:underline "
      >
        ← Zurück zu Mandanten
      </button>
    </div>
  );
}
