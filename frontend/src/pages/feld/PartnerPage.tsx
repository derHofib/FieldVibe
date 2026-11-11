import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardHat } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { partnerApi } from "../../api/endpoints";
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
  const uid = useId();
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const kannSehen = istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen");

  const [showForm, setShowForm] = useState(false);
  const [nameFehler, setNameFehler] = useState<string | null>(null);
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

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
        <div className="space-y-3 p-4">
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-sekundaer font-medium text-label2">
              Firmenname <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input id={`${uid}-0`}
              autoFocus
              required
              aria-invalid={!!nameFehler}
              aria-describedby={nameFehler ? `${uid}-name-fehler` : undefined}
              value={neuerPartner.name}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, name: e.target.value })}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            {nameFehler && (
              <p id={`${uid}-name-fehler`} role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                {nameFehler}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-sekundaer text-label2">
              Gewerk / was die Firma macht
            </label>
            <input id={`${uid}-1`}
              value={neuerPartner.gewerk}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, gewerk: e.target.value })}
              placeholder="z.B. Elektroinstallation, Trockenbau, Gerüstbau"
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-2`} className="mb-1 block text-sekundaer text-label2">Telefon</label>
            <input id={`${uid}-2`}
              value={neuerPartner.telefon}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, telefon: e.target.value })}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-3`} className="mb-1 block text-sekundaer text-label2">E-Mail</label>
            <input id={`${uid}-3`}
              type="email"
              value={neuerPartner.email}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, email: e.target.value })}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-4`} className="mb-1 block text-sekundaer text-label2">Straße + Hausnr.</label>
            <input id={`${uid}-4`}
              value={neuerPartner.strasse}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, strasse: e.target.value })}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor={`${uid}-5`} className="mb-1 block text-sekundaer text-label2">PLZ</label>
              <input id={`${uid}-5`}
                value={neuerPartner.plz}
                onChange={(e) => setNeuerPartner({ ...neuerPartner, plz: e.target.value })}
                className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
            </div>
            <div>
              <label htmlFor={`${uid}-6`} className="mb-1 block text-sekundaer text-label2">Ort</label>
              <input id={`${uid}-6`}
                value={neuerPartner.ort}
                onChange={(e) => setNeuerPartner({ ...neuerPartner, ort: e.target.value })}
                className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
            </div>
          </div>
          <div>
            <label htmlFor={`${uid}-7`} className="mb-1 block text-sekundaer text-label2">Notiz</label>
            <textarea id={`${uid}-7`}
              value={neuerPartner.notiz}
              onChange={(e) => setNeuerPartner({ ...neuerPartner, notiz: e.target.value })}
              rows={2}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <p className="text-sekundaer text-label2">
            Ansprechpartner und Nachweise (Freistellungsbescheinigung, Haftpflicht, ...) können
            anschließend auf der Partner-Detailseite hinterlegt werden.
          </p>
          <button
            disabled={createMutation.isPending}
            onClick={() => {
              if (!neuerPartner.name.trim()) {
                setNameFehler("Bitte einen Firmennamen eingeben.");
                return;
              }
              setNameFehler(null);
              createMutation.mutate();
            }}
            className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sekundaer font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
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
