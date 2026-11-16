import { useQuery } from "@tanstack/react-query";
import { HardHat } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { partnerApi } from "../../api/endpoints";
import { PartnerAnlegenFormular } from "../../components/PartnerAnlegenFormular";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { FehlerZustand } from "../../components/FehlerZustand";
import { AnlegenPanel } from "../../components/AnlegenPanel";

/** Partner-/Nachunternehmer-Verwaltung -- Firmen, denen einzelne Vorgaenge
 * (komplett oder als Teilleistung) delegiert werden koennen, siehe
 * VorgangDetailPage.tsx "Nachunternehmer"-Karte. Bewusst analog zur
 * Kundenverwaltung (KundenPage.tsx) aufgebaut. */
export function PartnerPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();

  const kannSehen = istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen");

  const [showForm, setShowForm] = useState(false);
  const [suche, setSuche] = useState("");

  const { data: partner, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: kannSehen,
  });
  const partnerGefiltert = (partner ?? []).filter((p) => {
    if (!suche.trim()) return true;
    const q = suche.trim().toLowerCase();
    return p.name.toLowerCase().includes(q) || (p.gewerk ?? "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      <h1 className="text-titel-mobil font-bold text-label">Partner &amp; Nachunternehmer</h1>

      <button
        onClick={() => setShowForm(true)}
        className="btn-touch btn-ap-primary px-4"
      >
        + Neuer Partner
      </button>

      <AnlegenPanel offen={showForm} titel="Neuer Partner" onClose={() => setShowForm(false)}>
        <PartnerAnlegenFormular
          onAngelegt={(p) => {
            setShowForm(false);
            navigate(`/partner/${p.id}`);
          }}
        />
      </AnlegenPanel>

      <div className="space-y-2">
        {(partner ?? []).length > 0 && (
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suche nach Name oder Gewerk…"
            className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
        )}
        {isLoading ? (
          <SkeletonList count={3} />
        ) : ladeFehler && !partner ? (
          <FehlerZustand fehler={ladeFehler} was="Die Partner" onErneut={() => void neuLaden()} />
        ) : (partner ?? []).length === 0 ? (
          <EmptyState icon={HardHat} text="Noch keine Partner/Nachunternehmer angelegt." />
        ) : partnerGefiltert.length === 0 ? (
          <p className="text-center text-sekundaer text-label2">
            Keine Partner gefunden für „{suche}".
          </p>
        ) : (
          partnerGefiltert.map((p) => (
            <button
              key={p.id}
              onClick={() => navigate(`/partner/${p.id}`)}
              className={`card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left ${
                p.aktiv ? "" : "opacity-60"
              }`}
            >
              <div>
                <div className="text-fliess font-medium text-label">{p.name}</div>
                {p.gewerk && (
                  <div className="text-sekundaer text-label2">{p.gewerk}</div>
                )}
              </div>
              {!p.aktiv && (
                <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-1 text-sekundaer text-label">
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
