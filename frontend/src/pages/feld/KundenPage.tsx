import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";

/** Eigenstaendige Kundenverwaltung -- vormals der "kunden"-Tab in der
 * inzwischen aufgeteilten GeschaeftPage (siehe Git-Historie). Rechnungen/
 * Angebote haben ihre eigenen Seiten (RechnungenPage/AngebotDetailPage-
 * Uebersicht), Material lebt jetzt in MaterialPage. */
export function KundenPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const kannSehen = istModulAktiv(currentUser, "kundenverwaltung") && hatRecht("kunden", "sehen");

  const [showForm, setShowForm] = useState(false);
  const [kundeFehler, setKundeFehler] = useState<string | null>(null);
  const [kundenSuche, setKundenSuche] = useState("");
  const [neuerKunde, setNeuerKunde] = useState({
    name: "",
    kundennummer: "",
    typ: "",
    strasse: "",
    plz: "",
    ort: "",
    notiz: "",
    ustIdnr: "",
  });

  const { data: kunden, isLoading: kundenLoading } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: kannSehen,
  });
  const kundenGefiltert = (kunden ?? []).filter((k) => {
    if (!kundenSuche.trim()) return true;
    const q = kundenSuche.trim().toLowerCase();
    return k.name.toLowerCase().includes(q) || (k.kundennummer ?? "").toLowerCase().includes(q);
  });

  const createKundeMutation = useMutation({
    mutationFn: () => {
      const adresse =
        neuerKunde.strasse || neuerKunde.plz || neuerKunde.ort
          ? { strasse: neuerKunde.strasse || undefined, plz: neuerKunde.plz || undefined, ort: neuerKunde.ort || undefined }
          : undefined;
      return kundenApi.create({
        name: neuerKunde.name,
        kundennummer: neuerKunde.kundennummer || undefined,
        typ: neuerKunde.typ || undefined,
        adresse,
        notiz: neuerKunde.notiz || undefined,
        ust_idnr: neuerKunde.ustIdnr || undefined,
      });
    },
    onSuccess: (kunde) => {
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      setShowForm(false);
      setKundeFehler(null);
      setNeuerKunde({ name: "", kundennummer: "", typ: "", strasse: "", plz: "", ort: "", notiz: "", ustIdnr: "" });
      navigate(`/kunden/${kunde.id}`);
    },
    onError: (err) =>
      setKundeFehler(err instanceof ApiError ? err.message : "Kunde konnte nicht angelegt werden."),
  });

  if (!kannSehen) return <Navigate to="/feed" replace />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-label">Kundenverwaltung</h1>
        {istModulAktiv(currentUser, "kundenportal") && (
          <button
            onClick={() => navigate("/anfragen")}
            className="btn-touch btn-ap px-3 py-1.5 text-xs font-semibold"
          >
            Auftragsanfragen
          </button>
        )}
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch btn-ap px-4 py-2 text-sm font-medium"
      >
        {showForm ? "Abbrechen" : "+ Neuer Kunde"}
      </button>

      {showForm && (
        <div className="space-y-3 border border-sep bg-card p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Name *</label>
            <input
              autoFocus
              value={neuerKunde.name}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, name: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-label2">
                Kundennummer (optional)
              </label>
              <input
                value={neuerKunde.kundennummer}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, kundennummer: e.target.value })}
                placeholder="wird sonst vergeben"
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-label2">Typ</label>
              <select
                value={neuerKunde.typ}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, typ: e.target.value })}
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                <option value="">Bitte wählen…</option>
                <option value="privat">Privat</option>
                <option value="gewerbe">Gewerbe</option>
                <option value="oeffentlich">Öffentlich</option>
                <option value="hausverwaltung">Hausverwaltung</option>
              </select>
            </div>
          </div>
          {(neuerKunde.typ === "gewerbe" || neuerKunde.typ === "oeffentlich") && (
            <div>
              <label className="mb-1 block text-xs text-label2">USt-IdNr.</label>
              <input
                value={neuerKunde.ustIdnr}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, ustIdnr: e.target.value })}
                placeholder="DE123456789"
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs text-label2">Straße + Hausnr.</label>
            <input
              value={neuerKunde.strasse}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, strasse: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-label2">PLZ</label>
              <input
                value={neuerKunde.plz}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, plz: e.target.value })}
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-label2">Ort</label>
              <input
                value={neuerKunde.ort}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, ort: e.target.value })}
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-label2">Notiz</label>
            <textarea
              value={neuerKunde.notiz}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, notiz: e.target.value })}
              rows={2}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <p className="text-xs text-label2">
            Ansprechpartner können anschließend auf der Kunden-Detailseite angelegt werden.
          </p>
          {kundeFehler && <p className="text-sm text-st-fehlt ">{kundeFehler}</p>}
          <button
            disabled={!neuerKunde.name.trim() || createKundeMutation.isPending}
            onClick={() => createKundeMutation.mutate()}
            className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      <div className="space-y-2">
        {(kunden ?? []).length > 0 && (
          <input
            value={kundenSuche}
            onChange={(e) => setKundenSuche(e.target.value)}
            placeholder="Suche nach Name oder Kundennummer…"
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
        )}
        {kundenLoading ? (
          <SkeletonList count={3} />
        ) : (kunden ?? []).length === 0 ? (
          <EmptyState icon={Users} text="Keine Kunden vorhanden." />
        ) : kundenGefiltert.length === 0 ? (
          <p className="text-center text-sm text-label2">
            Keine Kunden gefunden für „{kundenSuche}".
          </p>
        ) : (
          kundenGefiltert.map((k) => (
            <button
              key={k.id}
              onClick={() => navigate(`/kunden/${k.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between border border-sep bg-card p-3 text-left"
            >
              <div>
                <div className="text-xs text-label2">{k.kundennummer}</div>
                <div className="text-sm font-medium text-label">{k.name}</div>
              </div>
              {k.typ && (
                <span className="border border-sep px-2 py-1 text-xs font-semibold text-label">
                  {k.typ}
                </span>
              )}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
