import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardHat } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { partnerApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";

/** Partner-/Nachunternehmer-Verwaltung -- Firmen, denen einzelne Vorgaenge
 * (komplett oder als Teilleistung) delegiert werden koennen, siehe
 * VorgangDetailPage.tsx "Nachunternehmer"-Karte. Bewusst analog zur
 * Kundenverwaltung (KundenPage.tsx) aufgebaut. */
export function PartnerPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const kannSehen = istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen");

  const [showForm, setShowForm] = useState(false);
  const [suche, setSuche] = useState("");
  const [neuerPartner, setNeuerPartner] = useState({
    name: "",
    gewerk: "",
    telefon: "",
    email: "",
    strasse: "",
    plz: "",
    ort: "",
    notiz: "",
  });

  const { data: partner, isLoading } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: kannSehen,
  });
  const partnerGefiltert = (partner ?? []).filter((p) => {
    if (!suche.trim()) return true;
    const q = suche.trim().toLowerCase();
    return p.name.toLowerCase().includes(q) || (p.gewerk ?? "").toLowerCase().includes(q);
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const adresse =
        neuerPartner.strasse || neuerPartner.plz || neuerPartner.ort
          ? {
              strasse: neuerPartner.strasse || undefined,
              plz: neuerPartner.plz || undefined,
              ort: neuerPartner.ort || undefined,
            }
          : undefined;
      return partnerApi.create({
        name: neuerPartner.name,
        gewerk: neuerPartner.gewerk || undefined,
        telefon: neuerPartner.telefon || undefined,
        email: neuerPartner.email || undefined,
        adresse,
        notiz: neuerPartner.notiz || undefined,
      });
    },
    onSuccess: (p) => {
      queryClient.invalidateQueries({ queryKey: ["partner"] });
      setShowForm(false);
      setNeuerPartner({
        name: "",
        gewerk: "",
        telefon: "",
        email: "",
        strasse: "",
        plz: "",
        ort: "",
        notiz: "",
      });
      navigate(`/partner/${p.id}`);
    },
  });

  if (!kannSehen) return <Navigate to="/feed" replace />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ind-ink">Partner &amp; Nachunternehmer</h1>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
      >
        {showForm ? "Abbrechen" : "+ Neuer Partner"}
      </button>

      {showForm && (
        <div className="space-y-3 border border-ind-line bg-ind-bg p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">
              Firmenname *
            </label>
            <input
              autoFocus
              value={neuerPartner.name}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, name: e.target.value })}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ind-ink-3">
              Gewerk / was die Firma macht
            </label>
            <input
              value={neuerPartner.gewerk}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, gewerk: e.target.value })}
              placeholder="z.B. Elektroinstallation, Trockenbau, Gerüstbau"
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ind-ink-3">Telefon</label>
            <input
              value={neuerPartner.telefon}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, telefon: e.target.value })}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ind-ink-3">E-Mail</label>
            <input
              type="email"
              value={neuerPartner.email}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, email: e.target.value })}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ind-ink-3">Straße + Hausnr.</label>
            <input
              value={neuerPartner.strasse}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, strasse: e.target.value })}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">PLZ</label>
              <input
                value={neuerPartner.plz}
                onChange={(e) => setNeuerPartner({ ...neuerPartner, plz: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">Ort</label>
              <input
                value={neuerPartner.ort}
                onChange={(e) => setNeuerPartner({ ...neuerPartner, ort: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-ind-ink-3">Notiz</label>
            <textarea
              value={neuerPartner.notiz}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, notiz: e.target.value })}
              rows={2}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <p className="text-xs text-ind-ink-3">
            Ansprechpartner und Nachweise (Freistellungsbescheinigung, Haftpflicht, ...) können
            anschließend auf der Partner-Detailseite hinterlegt werden.
          </p>
          <button
            disabled={!neuerPartner.name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      <div className="space-y-2">
        {(partner ?? []).length > 0 && (
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suche nach Name oder Gewerk…"
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        )}
        {isLoading ? (
          <SkeletonList count={3} />
        ) : (partner ?? []).length === 0 ? (
          <EmptyState icon={HardHat} text="Noch keine Partner/Nachunternehmer angelegt." />
        ) : partnerGefiltert.length === 0 ? (
          <p className="text-center text-sm text-ind-ink-3">
            Keine Partner gefunden für „{suche}".
          </p>
        ) : (
          partnerGefiltert.map((p) => (
            <button
              key={p.id}
              onClick={() => navigate(`/partner/${p.id}`)}
              className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                p.aktiv ? "" : "opacity-60"
              }`}
            >
              <div>
                <div className="text-sm font-medium text-ind-ink">{p.name}</div>
                {p.gewerk && (
                  <div className="text-xs text-ind-ink-3">{p.gewerk}</div>
                )}
              </div>
              {!p.aktiv && (
                <span className="rounded-full bg-slate-200 px-2 py-1 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                  inaktiv
                </span>
              )}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
