import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { angeboteApi, anlagenApi, bestellungenApi, lieferantenApi, materialApi, materialBedarfeApi, tagsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { Anlage, AnlagenObjekttyp, BestellungStatus, Material, MaterialBedarfZweck, Tag } from "../../types";

type MaterialTab = "material" | "bestellwesen";

const BESTELLUNG_STATUS_LABEL: Record<BestellungStatus, string> = {
  entwurf: "Entwurf",
  bestellt: "Bestellt",
  eingegangen: "Eingegangen",
};

const OBJEKTTYP_LABEL: Record<AnlagenObjekttyp, string> = {
  kundenanlage: "Kundenanlage",
  fahrzeug: "Fahrzeug",
  lager: "Lager",
  baustelle: "Baustelle",
};

function istUnterbestand(m: Material): boolean {
  return Number(m.bestand_gesamt) <= Number(m.mindestbestand);
}

function MaterialZeile({
  material,
  lagerorte,
  lieferantName,
  tags,
}: {
  material: Material;
  lagerorte: Anlage[];
  lieferantName?: string;
  tags: Tag[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editingLagerId, setEditingLagerId] = useState<string | null>(null);
  const [neueMenge, setNeueMenge] = useState("");
  const [zeigeUmlagern, setZeigeUmlagern] = useState(false);
  const [umlagernVon, setUmlagernVon] = useState("");
  const [umlagernNach, setUmlagernNach] = useState("");
  const [umlagernMenge, setUmlagernMenge] = useState("");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["material"] });
    queryClient.invalidateQueries({ queryKey: ["stories"] });
  };

  const bestandSetzenMutation = useMutation({
    mutationFn: (lagerId: string) => materialApi.bestandSetzen(material.id, lagerId, neueMenge),
    onSuccess: () => {
      setEditingLagerId(null);
      invalidate();
    },
  });

  const umlagernMutation = useMutation({
    mutationFn: () => materialApi.umlagern(material.id, umlagernVon, umlagernNach, umlagernMenge),
    onSuccess: () => {
      setZeigeUmlagern(false);
      setUmlagernVon("");
      setUmlagernNach("");
      setUmlagernMenge("");
      invalidate();
    },
  });

  return (
    <div className="card-interactive border border-ind-line bg-ind-bg p-3">
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate(`/material/${material.id}`)}
          className="btn-touch text-left"
        >
          <div className="text-sm font-medium text-slate-800 underline-offset-2 hover:underline dark:text-stone-100">
            {material.bezeichnung}
          </div>
          <div
            className={`text-xs ${
              istUnterbestand(material)
                ? "font-semibold text-red-600 dark:text-red-400"
                : "text-ind-ink-3"
            }`}
          >
            Gesamt: {material.bestand_gesamt} {material.einheit} (Mindestbestand {material.mindestbestand})
          </div>
          {material.artikelnummer && (
            <div className="text-xs text-ind-ink-3">Art.-Nr. {material.artikelnummer}</div>
          )}
          {material.einzelpreis && (
            <div className="text-xs text-ind-ink-3">
              {material.einzelpreis} EUR/Einheit{lieferantName ? ` · ${lieferantName}` : ""}
            </div>
          )}
          {!material.einzelpreis && lieferantName && (
            <div className="text-xs text-ind-ink-3">{lieferantName}</div>
          )}
          {tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {tags.map((t) => (
                <span
                  key={t.id}
                  className="border border-ind-line px-1.5 py-0.5 text-xs text-ind-ink-2"
                >
                  #{t.label}
                </span>
              ))}
            </div>
          )}
        </button>
        {lagerorte.length > 1 && (
          <button
            onClick={() => setZeigeUmlagern((v) => !v)}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            {zeigeUmlagern ? "Abbrechen" : "Umlagern"}
          </button>
        )}
      </div>

      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 dark:border-stone-800">
        {material.bestaende.map((b) => (
          <div key={b.lager_id} className="flex items-center justify-between text-xs">
            <span className="text-ind-ink-2">{b.lager_bezeichnung}</span>
            {editingLagerId === b.lager_id ? (
              <span className="flex items-center gap-1">
                <input
                  type="number"
                  step="0.01"
                  value={neueMenge}
                  onChange={(e) => setNeueMenge(e.target.value)}
                  className="w-16 rounded-xs border border-slate-300 px-1 py-0.5 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <button
                  onClick={() => bestandSetzenMutation.mutate(b.lager_id)}
                  disabled={bestandSetzenMutation.isPending}
                  className="btn-touch rounded-xs btn-industry btn-industry-primary px-2 py-0.5"
                >
                  ✓
                </button>
                <button
                  onClick={() => setEditingLagerId(null)}
                  className="btn-touch text-ind-ink-3"
                >
                  ✕
                </button>
              </span>
            ) : (
              <button
                onClick={() => {
                  setEditingLagerId(b.lager_id);
                  setNeueMenge(b.menge);
                }}
                className="btn-touch font-medium text-slate-700 underline-offset-2 hover:underline dark:text-stone-300"
              >
                {b.menge} {material.einheit}
              </button>
            )}
          </div>
        ))}
      </div>

      {zeigeUmlagern && (
        <div className="mt-2 space-y-2 border border-ind-line-2 p-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={umlagernVon}
              onChange={(e) => setUmlagernVon(e.target.value)}
              className="border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
            >
              <option value="">Von…</option>
              {lagerorte.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.bezeichnung}
                </option>
              ))}
            </select>
            <select
              value={umlagernNach}
              onChange={(e) => setUmlagernNach(e.target.value)}
              className="border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
            >
              <option value="">Nach…</option>
              {lagerorte.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.bezeichnung}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <input
              type="number"
              step="0.01"
              placeholder="Menge"
              value={umlagernMenge}
              onChange={(e) => setUmlagernMenge(e.target.value)}
              className="flex-1 border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
            />
            <button
              disabled={
                !umlagernVon || !umlagernNach || umlagernVon === umlagernNach || !umlagernMenge || umlagernMutation.isPending
              }
              onClick={() => umlagernMutation.mutate()}
              className="btn-touch shrink-0 rounded-md btn-industry btn-industry-primary px-3 py-1 text-xs font-medium disabled:opacity-50"
            >
              Umlagern
            </button>
          </div>
          {umlagernMutation.isError && (
            <p className="text-xs text-red-700 dark:text-red-400">
              {umlagernMutation.error instanceof ApiError ? umlagernMutation.error.message : "Fehler"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function LagerorteVerwaltung({ lagerorte }: { lagerorte: Anlage[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [objekttyp, setObjekttyp] = useState<AnlagenObjekttyp>("fahrzeug");

  const createMutation = useMutation({
    mutationFn: () => anlagenApi.create({ bezeichnung, objekttyp }),
    onSuccess: () => {
      setShowForm(false);
      setBezeichnung("");
      queryClient.invalidateQueries({ queryKey: ["lagerorte"] });
    },
  });

  return (
    <div className="border border-ind-line bg-ind-bg p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ind-ink-3">Fahrzeuge & Lagerorte</h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
        >
          {showForm ? "Abbrechen" : "+ Neu"}
        </button>
      </div>

      {lagerorte.length === 0 ? (
        <p className="mt-2 text-sm text-ind-ink-3">Noch keine weiteren Lagerorte.</p>
      ) : (
        <div className="mt-2 space-y-1">
          {lagerorte.map((l) => (
            <button
              key={l.id}
              onClick={() => navigate(`/anlagen/${l.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm dark:bg-stone-800"
            >
              <span className="text-ind-ink">{l.bezeichnung}</span>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                {OBJEKTTYP_LABEL[l.objekttyp]}
              </span>
            </button>
          ))}
        </div>
      )}

      {showForm && (
        <div className="mt-2 space-y-2 border-t border-slate-100 pt-2 dark:border-stone-800">
          <input
            value={bezeichnung}
            onChange={(e) => setBezeichnung(e.target.value)}
            placeholder="Bezeichnung (z.B. Transporter VW)"
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
          <select
            value={objekttyp}
            onChange={(e) => setObjekttyp(e.target.value as AnlagenObjekttyp)}
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          >
            <option value="fahrzeug">Fahrzeug</option>
            <option value="lager">Lager</option>
            <option value="baustelle">Baustelle</option>
          </select>
          <p className="text-xs text-ind-ink-3">
            Jedes Fahrzeug/Lager ist automatisch ein eigener Lagerort für Material -- keine Kunde-
            Zuordnung nötig.
          </p>
          <button
            disabled={!bezeichnung || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}
    </div>
  );
}

/** Eigenstaendige Material-/Lagerverwaltung -- vormals die Tabs "material"
 * und "bestellwesen" in der aufgeteilten GeschaeftPage. Kunden haben ihre
 * eigene Seite (KundenPage), Rechnungen/Angebote ihre bestehenden. */
export function MaterialPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const materialAktiv = istModulAktiv(currentUser, "material");

  const [tab, setTab] = useState<MaterialTab>("material");
  const [showForm, setShowForm] = useState(false);
  const [materialForm, setMaterialForm] = useState({
    bezeichnung: "",
    einheit: "Stk",
    menge: "0",
    lagerId: "",
    mindestbestand: "0",
    einzelpreis: "",
    lieferantId: "",
  });
  const [matFilterLieferantId, setMatFilterLieferantId] = useState("");
  const [matFilterTagId, setMatFilterTagId] = useState("");
  const [matFilterUnterbestand, setMatFilterUnterbestand] = useState(false);
  const [matSuche, setMatSuche] = useState("");
  const [bedarfZweck, setBedarfZweck] = useState<MaterialBedarfZweck>("bestellung");
  const [ausgewaehlteBedarfe, setAusgewaehlteBedarfe] = useState<Set<string>>(new Set());
  const [bestellLieferantId, setBestellLieferantId] = useState("");
  const [showLieferantForm, setShowLieferantForm] = useState(false);
  const [lieferantName, setLieferantName] = useState("");
  const [lieferantEmail, setLieferantEmail] = useState("");

  const bestellwesenAktiv = tab === "bestellwesen" && materialAktiv;

  const { data: material, isLoading: materialLoading } = useQuery({
    queryKey: ["material"],
    queryFn: () => materialApi.list(),
    enabled: materialAktiv,
  });
  const { data: alleAnlagen } = useQuery({
    queryKey: ["lagerorte"],
    queryFn: () => anlagenApi.list(),
    enabled: tab === "material" && materialAktiv,
  });
  const lagerorte = (alleAnlagen ?? []).filter((a) => a.objekttyp !== "kundenanlage");
  const { data: materialTags } = useQuery({
    queryKey: ["tags"],
    queryFn: tagsApi.list,
    enabled: materialAktiv,
  });
  const materialGefiltert = (material ?? []).filter((m) => {
    if (matFilterLieferantId && m.lieferant_id !== matFilterLieferantId) return false;
    if (matFilterTagId && !m.tag_ids.includes(matFilterTagId)) return false;
    if (matFilterUnterbestand && !istUnterbestand(m)) return false;
    if (matSuche.trim()) {
      const q = matSuche.trim().toLowerCase();
      const treffer =
        m.bezeichnung.toLowerCase().includes(q) || (m.artikelnummer ?? "").toLowerCase().includes(q);
      if (!treffer) return false;
    }
    return true;
  });

  const { data: offeneBedarfe } = useQuery({
    queryKey: ["material-bedarfe", "offen", bedarfZweck],
    queryFn: () => materialBedarfeApi.list({ status: "offen", zweck: bedarfZweck }),
    enabled: bestellwesenAktiv,
  });
  const { data: bestellungen } = useQuery({
    queryKey: ["bestellungen"],
    queryFn: () => bestellungenApi.list(),
    enabled: bestellwesenAktiv,
  });
  const { data: lieferanten } = useQuery({
    queryKey: ["lieferanten"],
    queryFn: () => lieferantenApi.list(),
    enabled: bestellwesenAktiv || (tab === "material" && materialAktiv),
  });

  useEffect(() => {
    setAusgewaehlteBedarfe(new Set());
  }, [bedarfZweck]);

  const toggleBedarf = (id: string) =>
    setAusgewaehlteBedarfe((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const bestellungErstellenMutation = useMutation({
    mutationFn: () =>
      bestellungenApi.createFromBedarfe(Array.from(ausgewaehlteBedarfe), bestellLieferantId || undefined),
    onSuccess: (bestellung) => {
      setAusgewaehlteBedarfe(new Set());
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "offen", "bestellung"] });
      queryClient.invalidateQueries({ queryKey: ["bestellungen"] });
      navigate(`/bestellungen/${bestellung.id}`);
    },
  });

  const angebotAusBedarfenMutation = useMutation({
    mutationFn: () => angeboteApi.createFromMaterialBedarfe(Array.from(ausgewaehlteBedarfe)),
    onSuccess: (angebot) => {
      setAusgewaehlteBedarfe(new Set());
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "offen", "angebot"] });
      navigate(`/angebote/${angebot.id}`);
    },
  });

  const createLieferantMutation = useMutation({
    mutationFn: () => lieferantenApi.create({ name: lieferantName, email: lieferantEmail || undefined }),
    onSuccess: () => {
      setLieferantName("");
      setLieferantEmail("");
      setShowLieferantForm(false);
      queryClient.invalidateQueries({ queryKey: ["lieferanten"] });
    },
  });

  const deleteLieferantMutation = useMutation({
    mutationFn: (id: string) => lieferantenApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lieferanten"] }),
  });

  const kannLieferantenLoeschen = currentUser?.role === "loesch_operativ";

  const createMaterialMutation = useMutation({
    mutationFn: () =>
      materialApi.create({
        bezeichnung: materialForm.bezeichnung,
        einheit: materialForm.einheit,
        menge: materialForm.menge,
        lager_id: materialForm.lagerId || undefined,
        mindestbestand: materialForm.mindestbestand,
        einzelpreis: materialForm.einzelpreis || undefined,
        lieferant_id: materialForm.lieferantId || undefined,
      }),
    onSuccess: () => {
      setShowForm(false);
      setMaterialForm({
        bezeichnung: "",
        einheit: "Stk",
        menge: "0",
        lagerId: "",
        mindestbestand: "0",
        einzelpreis: "",
        lieferantId: "",
      });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  if (!materialAktiv) return <Navigate to="/feed" replace />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ind-ink">Material</h1>

      <div className="flex gap-2 overflow-x-auto border border-ind-line bg-ind-bg p-1">
        {(["material", "bestellwesen"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setShowForm(false);
            }}
            className={`btn-touch shrink-0 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium capitalize ${
              tab === t
                ? "btn-industry btn-industry-primary text-white"
                : "text-ind-ink-2"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "material" && (
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
        >
          {showForm ? "Abbrechen" : "+ Neues Material"}
        </button>
      )}

      {showForm && tab === "material" && (
        <div className="space-y-3 border border-ind-line bg-ind-bg p-4">
          <input
            value={materialForm.bezeichnung}
            onChange={(e) => setMaterialForm({ ...materialForm, bezeichnung: e.target.value })}
            placeholder="Bezeichnung"
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">Einheit</label>
              <input
                value={materialForm.einheit}
                onChange={(e) => setMaterialForm({ ...materialForm, einheit: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">
                Einzelpreis (EUR, optional)
              </label>
              <input
                type="number"
                step="0.01"
                value={materialForm.einzelpreis}
                onChange={(e) => setMaterialForm({ ...materialForm, einzelpreis: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">Anfangsbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.menge}
                onChange={(e) => setMaterialForm({ ...materialForm, menge: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ind-ink-3">Mindestbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.mindestbestand}
                onChange={(e) => setMaterialForm({ ...materialForm, mindestbestand: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-ind-ink-3">
                Standard-Lieferant (optional)
              </label>
              <select
                value={materialForm.lieferantId}
                onChange={(e) => setMaterialForm({ ...materialForm, lieferantId: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              >
                <option value="">Kein Lieferant hinterlegt</option>
                {(lieferanten ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-ind-ink-3">
                Lagerort für Anfangsbestand
              </label>
              <select
                value={materialForm.lagerId}
                onChange={(e) => setMaterialForm({ ...materialForm, lagerId: e.target.value })}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              >
                <option value="">Zentrallager (Standard)</option>
                {lagerorte
                  .filter((l) => l.objekttyp !== "kundenanlage")
                  .map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.bezeichnung}
                    </option>
                  ))}
              </select>
            </div>
          </div>
          <button
            disabled={!materialForm.bezeichnung || createMaterialMutation.isPending}
            onClick={() => createMaterialMutation.mutate()}
            className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {tab === "material" && (
        <div className="space-y-2">
          <LagerorteVerwaltung lagerorte={lagerorte.filter((l) => l.objekttyp !== "lager" || l.bezeichnung !== "Zentrallager")} />

          {(material ?? []).length > 0 && (
            <div className="space-y-2 border border-ind-line bg-ind-bg p-3">
              <input
                value={matSuche}
                onChange={(e) => setMatSuche(e.target.value)}
                placeholder="Suche nach Bezeichnung oder Artikelnummer…"
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={matFilterLieferantId}
                  onChange={(e) => setMatFilterLieferantId(e.target.value)}
                  className="border border-ind-line bg-transparent px-2 py-1.5 text-xs text-ind-ink"
                >
                  <option value="">Alle Lieferanten</option>
                  {(lieferanten ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
                <select
                  value={matFilterTagId}
                  onChange={(e) => setMatFilterTagId(e.target.value)}
                  className="border border-ind-line bg-transparent px-2 py-1.5 text-xs text-ind-ink"
                >
                  <option value="">Alle Tags</option>
                  {(materialTags ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      #{t.label}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-1.5 text-xs text-ind-ink-2">
                <input
                  type="checkbox"
                  checked={matFilterUnterbestand}
                  onChange={(e) => setMatFilterUnterbestand(e.target.checked)}
                  className="h-3.5 w-3.5"
                />
                Nur Unterbestand
              </label>
            </div>
          )}

          {materialLoading ? (
            <SkeletonList count={3} />
          ) : (material ?? []).length === 0 ? (
            <EmptyState icon={Package} text="Kein Material erfasst." />
          ) : materialGefiltert.length === 0 ? (
            <p className="text-center text-sm text-ind-ink-3">Kein Material entspricht dem Filter.</p>
          ) : (
            materialGefiltert.map((m) => (
              <MaterialZeile
                key={m.id}
                material={m}
                lagerorte={lagerorte}
                lieferantName={lieferanten?.find((l) => l.id === m.lieferant_id)?.name}
                tags={(materialTags ?? []).filter((t) => m.tag_ids.includes(t.id))}
              />
            ))
          )}
        </div>
      )}

      {tab === "bestellwesen" && (
        <div className="space-y-4">
          <div className="border border-ind-line bg-ind-bg p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ind-ink-3">Lieferanten</h2>
              <button
                onClick={() => setShowLieferantForm((v) => !v)}
                className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
              >
                {showLieferantForm ? "Abbrechen" : "+ Neu"}
              </button>
            </div>
            {showLieferantForm && (
              <div className="mb-2 space-y-2 border border-ind-line-2 p-2">
                <input
                  value={lieferantName}
                  onChange={(e) => setLieferantName(e.target.value)}
                  placeholder="Name"
                  className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                />
                <input
                  value={lieferantEmail}
                  onChange={(e) => setLieferantEmail(e.target.value)}
                  placeholder="E-Mail (optional)"
                  className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                />
                <button
                  disabled={!lieferantName.trim() || createLieferantMutation.isPending}
                  onClick={() => createLieferantMutation.mutate()}
                  className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  Anlegen
                </button>
              </div>
            )}
            {(lieferanten ?? []).length === 0 ? (
              <p className="text-sm text-ind-ink-3">Noch keine Lieferanten angelegt.</p>
            ) : (
              <div className="space-y-1">
                {lieferanten!.map((l) => (
                  <div
                    key={l.id}
                    className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
                  >
                    <div>
                      <span className="text-ind-ink">{l.name}</span>
                      {l.email && <span className="ml-2 text-xs text-ind-ink-3">{l.email}</span>}
                    </div>
                    {kannLieferantenLoeschen && (
                      <button
                        onClick={() => {
                          if (window.confirm(`Lieferant "${l.name}" wirklich löschen?`)) {
                            deleteLieferantMutation.mutate(l.id);
                          }
                        }}
                        disabled={deleteLieferantMutation.isPending}
                        className="btn-touch text-xs font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
                      >
                        Löschen
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border border-ind-line bg-ind-bg p-3">
            <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">Offene Materialbedarfe</h2>
            <div className="mb-2 flex gap-2 rounded-md bg-slate-100 p-1 dark:bg-stone-800">
              <button
                onClick={() => setBedarfZweck("bestellung")}
                className={`btn-touch flex-1 rounded-md py-1.5 text-xs font-medium ${
                  bedarfZweck === "bestellung"
                    ? "bg-white text-slate-800 shadow-xs dark:bg-stone-700 dark:text-stone-100"
                    : "text-ind-ink-3"
                }`}
              >
                Zur Bestellung
              </button>
              <button
                onClick={() => setBedarfZweck("angebot")}
                className={`btn-touch flex-1 rounded-md py-1.5 text-xs font-medium ${
                  bedarfZweck === "angebot"
                    ? "bg-white text-slate-800 shadow-xs dark:bg-stone-700 dark:text-stone-100"
                    : "text-ind-ink-3"
                }`}
              >
                Für Angebot
              </button>
            </div>

            {(offeneBedarfe ?? []).length === 0 ? (
              <p className="text-sm text-ind-ink-3">Keine offenen Materialbedarfe.</p>
            ) : (
              <div className="space-y-1">
                {offeneBedarfe!.map((b) => (
                  <label
                    key={b.id}
                    className="flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
                  >
                    <input
                      type="checkbox"
                      checked={ausgewaehlteBedarfe.has(b.id)}
                      onChange={() => toggleBedarf(b.id)}
                      className="h-4 w-4"
                    />
                    <span className="flex-1 text-ind-ink">
                      {b.menge} {b.material_einheit} {b.material_bezeichnung}
                      <span className="ml-1.5 text-xs text-ind-ink-3">
                        {b.vorgang_vorgangsnummer} · {b.kunde_name}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}

            {ausgewaehlteBedarfe.size > 0 && bedarfZweck === "bestellung" && (
              <div className="mt-2 space-y-2 border-t border-slate-100 pt-2 dark:border-stone-800">
                <select
                  value={bestellLieferantId}
                  onChange={(e) => setBestellLieferantId(e.target.value)}
                  className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                >
                  <option value="">Kein Lieferant hinterlegt</option>
                  {(lieferanten ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
                <button
                  disabled={bestellungErstellenMutation.isPending}
                  onClick={() => bestellungErstellenMutation.mutate()}
                  className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  Bestellung aus {ausgewaehlteBedarfe.size} Position(en) erstellen
                </button>
              </div>
            )}
            {ausgewaehlteBedarfe.size > 0 && bedarfZweck === "angebot" && (
              <div className="mt-2 border-t border-slate-100 pt-2 dark:border-stone-800">
                <button
                  disabled={angebotAusBedarfenMutation.isPending}
                  onClick={() => angebotAusBedarfenMutation.mutate()}
                  className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  Angebot aus {ausgewaehlteBedarfe.size} Position(en) erstellen
                </button>
              </div>
            )}
          </div>

          <div className="border border-ind-line bg-ind-bg p-3">
            <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">Bestellungen</h2>
            {(bestellungen ?? []).length === 0 ? (
              <p className="text-sm text-ind-ink-3">Noch keine Bestellungen vorhanden.</p>
            ) : (
              <div className="space-y-1">
                {bestellungen!.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => navigate(`/bestellungen/${b.id}`)}
                    className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm dark:bg-stone-800"
                  >
                    <span className="text-ind-ink">{b.bestellnummer}</span>
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                      {BESTELLUNG_STATUS_LABEL[b.status]}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
