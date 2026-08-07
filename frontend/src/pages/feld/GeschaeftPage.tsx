import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Package, Receipt, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  angeboteApi,
  anlagenApi,
  bestellungenApi,
  kundenApi,
  lieferantenApi,
  materialApi,
  materialBedarfeApi,
  rechnungenApi,
  tagsApi,
} from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type {
  Anlage,
  AnlagenObjekttyp,
  AngebotStatus,
  BestellungStatus,
  Material,
  MaterialBedarfZweck,
  RechnungStatus,
  Tag,
} from "../../types";

type GeschaeftTab = "kunden" | "angebote" | "rechnungen" | "material" | "bestellwesen";

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

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
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
    <div className="card-interactive rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
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
                : "text-slate-500 dark:text-stone-400"
            }`}
          >
            Gesamt: {material.bestand_gesamt} {material.einheit} (Mindestbestand {material.mindestbestand})
          </div>
          {material.artikelnummer && (
            <div className="text-xs text-slate-400 dark:text-stone-500">Art.-Nr. {material.artikelnummer}</div>
          )}
          {material.einzelpreis && (
            <div className="text-xs text-slate-400 dark:text-stone-500">
              {material.einzelpreis} EUR/Einheit{lieferantName ? ` · ${lieferantName}` : ""}
            </div>
          )}
          {!material.einzelpreis && lieferantName && (
            <div className="text-xs text-slate-400 dark:text-stone-500">{lieferantName}</div>
          )}
          {tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {tags.map((t) => (
                <span
                  key={t.id}
                  className="rounded-full bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-stone-800 dark:text-stone-400"
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
            <span className="text-slate-600 dark:text-stone-300">{b.lager_bezeichnung}</span>
            {editingLagerId === b.lager_id ? (
              <span className="flex items-center gap-1">
                <input
                  type="number"
                  step="0.01"
                  value={neueMenge}
                  onChange={(e) => setNeueMenge(e.target.value)}
                  className="w-16 rounded border border-slate-300 px-1 py-0.5 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <button
                  onClick={() => bestandSetzenMutation.mutate(b.lager_id)}
                  disabled={bestandSetzenMutation.isPending}
                  className="btn-touch rounded btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-2 py-0.5 text-white"
                >
                  ✓
                </button>
                <button
                  onClick={() => setEditingLagerId(null)}
                  className="btn-touch text-slate-400 dark:text-stone-500"
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
        <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={umlagernVon}
              onChange={(e) => setUmlagernVon(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
              className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <button
              disabled={
                !umlagernVon || !umlagernNach || umlagernVon === umlagernNach || !umlagernMenge || umlagernMutation.isPending
              }
              onClick={() => umlagernMutation.mutate()}
              className="btn-touch shrink-0 rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
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
    <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Fahrzeuge & Lagerorte</h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
        >
          {showForm ? "Abbrechen" : "+ Neu"}
        </button>
      </div>

      {lagerorte.length === 0 ? (
        <p className="mt-2 text-sm text-slate-400 dark:text-stone-500">Noch keine weiteren Lagerorte.</p>
      ) : (
        <div className="mt-2 space-y-1">
          {lagerorte.map((l) => (
            <button
              key={l.id}
              onClick={() => navigate(`/anlagen/${l.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm dark:bg-stone-800"
            >
              <span className="text-slate-700 dark:text-stone-200">{l.bezeichnung}</span>
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
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
          <select
            value={objekttyp}
            onChange={(e) => setObjekttyp(e.target.value as AnlagenObjekttyp)}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="fahrzeug">Fahrzeug</option>
            <option value="lager">Lager</option>
            <option value="baustelle">Baustelle</option>
          </select>
          <p className="text-xs text-slate-400 dark:text-stone-500">
            Jedes Fahrzeug/Lager ist automatisch ein eigener Lagerort für Material -- keine Kunde-
            Zuordnung nötig.
          </p>
          <button
            disabled={!bezeichnung || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}
    </div>
  );
}

export function GeschaeftPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sichtbareTabs: GeschaeftTab[] = [
    ...(istModulAktiv(currentUser, "kundenverwaltung") ? (["kunden"] as const) : []),
    ...(istModulAktiv(currentUser, "abrechnung") ? (["angebote", "rechnungen"] as const) : []),
    ...(istModulAktiv(currentUser, "material") ? (["material", "bestellwesen"] as const) : []),
  ];
  const [tab, setTab] = useState<GeschaeftTab>(sichtbareTabs[0] ?? "kunden");
  useEffect(() => {
    if (sichtbareTabs.length > 0 && !sichtbareTabs.includes(tab)) {
      setTab(sichtbareTabs[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sichtbareTabs.join(",")]);
  const [showForm, setShowForm] = useState(false);
  const [kundeId, setKundeId] = useState("");
  const [betragNetto, setBetragNetto] = useState("");
  const [leistungsdatum, setLeistungsdatum] = useState("");
  const [neuerKunde, setNeuerKunde] = useState({
    name: "",
    kundennummer: "",
    typ: "",
    strasse: "",
    plz: "",
    ort: "",
    notiz: "",
  });
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
  const [kundenSuche, setKundenSuche] = useState("");
  const [bedarfZweck, setBedarfZweck] = useState<MaterialBedarfZweck>("bestellung");
  const [ausgewaehlteBedarfe, setAusgewaehlteBedarfe] = useState<Set<string>>(new Set());
  const [bestellLieferantId, setBestellLieferantId] = useState("");
  const [showLieferantForm, setShowLieferantForm] = useState(false);
  const [lieferantName, setLieferantName] = useState("");
  const [lieferantEmail, setLieferantEmail] = useState("");

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const materialAktiv = istModulAktiv(currentUser, "material");
  const bestellwesenAktiv = tab === "bestellwesen" && materialAktiv;

  const { data: kunden, isLoading: kundenLoading } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
  });
  const kundenGefiltert = (kunden ?? []).filter((k) => {
    if (!kundenSuche.trim()) return true;
    const q = kundenSuche.trim().toLowerCase();
    return k.name.toLowerCase().includes(q) || (k.kundennummer ?? "").toLowerCase().includes(q);
  });
  const { data: angebote, isLoading: angeboteLoading } = useQuery({
    queryKey: ["angebote"],
    queryFn: () => angeboteApi.list(),
    enabled: abrechnungAktiv,
  });
  const { data: rechnungen, isLoading: rechnungenLoading } = useQuery({
    queryKey: ["rechnungen"],
    queryFn: () => rechnungenApi.list(),
    enabled: abrechnungAktiv,
  });
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

  const createAngebotMutation = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate(`/angebote/${angebot.id}`);
    },
  });

  const createRechnungMutation = useMutation({
    mutationFn: () =>
      rechnungenApi.create({
        kunde_id: kundeId,
        betrag_netto: betragNetto,
        leistungsdatum: leistungsdatum || undefined,
      }),
    onSuccess: (rechnung) => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate(`/rechnungen/${rechnung.id}`);
    },
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
      });
    },
    onSuccess: (kunde) => {
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      setShowForm(false);
      setNeuerKunde({ name: "", kundennummer: "", typ: "", strasse: "", plz: "", ort: "", notiz: "" });
      navigate(`/kunden/${kunde.id}`);
    },
  });

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

  if (currentUser && !hatRecht("dispo", "sehen")) return <Navigate to="/feed" replace />;
  if (sichtbareTabs.length === 0) return <Navigate to="/feed" replace />;

  const nameFuer = (kundeId: string) => kunden?.find((k) => k.id === kundeId)?.name ?? "—";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Geschäft</h1>
        {istModulAktiv(currentUser, "kundenportal") && (
          <button
            onClick={() => navigate("/anfragen")}
            className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300"
          >
            Auftragsanfragen
          </button>
        )}
      </div>

      <div className="flex gap-2 overflow-x-auto rounded-lg bg-white p-1 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        {sichtbareTabs.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setShowForm(false);
            }}
            className={`btn-touch shrink-0 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium capitalize ${
              tab === t
                ? "btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                : "text-slate-600 dark:text-stone-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab !== "bestellwesen" && (
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
        >
          {showForm
            ? "Abbrechen"
            : tab === "kunden"
              ? "+ Neuer Kunde"
              : tab === "angebote"
                ? "+ Neues Angebot"
                : tab === "rechnungen"
                  ? "+ Neue Rechnung"
                  : "+ Neues Material"}
        </button>
      )}

      {showForm && tab === "kunden" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">Name *</label>
            <input
              autoFocus
              value={neuerKunde.name}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, name: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">
                Kundennummer (optional)
              </label>
              <input
                value={neuerKunde.kundennummer}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, kundennummer: e.target.value })}
                placeholder="wird sonst vergeben"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Typ</label>
              <select
                value={neuerKunde.typ}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, typ: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              >
                <option value="">Bitte wählen…</option>
                <option value="privat">Privat</option>
                <option value="gewerbe">Gewerbe</option>
                <option value="oeffentlich">Öffentlich</option>
                <option value="hausverwaltung">Hausverwaltung</option>
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Straße + Hausnr.</label>
            <input
              value={neuerKunde.strasse}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, strasse: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">PLZ</label>
              <input
                value={neuerKunde.plz}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, plz: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Ort</label>
              <input
                value={neuerKunde.ort}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, ort: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Notiz</label>
            <textarea
              value={neuerKunde.notiz}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, notiz: e.target.value })}
              rows={2}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <p className="text-xs text-slate-400 dark:text-stone-500">
            Ansprechpartner können anschließend auf der Kunden-Detailseite angelegt werden.
          </p>
          <button
            disabled={!neuerKunde.name.trim() || createKundeMutation.isPending}
            onClick={() => createKundeMutation.mutate()}
            className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {showForm && tab !== "material" && tab !== "kunden" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">Kunde</label>
            <select
              value={kundeId}
              onChange={(e) => setKundeId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              <option value="">Bitte wählen…</option>
              {kunden?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.kundennummer})
                </option>
              ))}
            </select>
          </div>
          {tab === "rechnungen" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">
                  Betrag netto (EUR)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={betragNetto}
                  onChange={(e) => setBetragNetto(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">
                  Leistungsdatum (optional)
                </label>
                <input
                  type="date"
                  value={leistungsdatum}
                  onChange={(e) => setLeistungsdatum(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">
                  Nur nötig, wenn abweichend vom Rechnungsdatum.
                </p>
              </div>
            </>
          )}
          <button
            disabled={
              !kundeId ||
              (tab === "rechnungen" && !betragNetto) ||
              createAngebotMutation.isPending ||
              createRechnungMutation.isPending
            }
            onClick={() => (tab === "angebote" ? createAngebotMutation.mutate() : createRechnungMutation.mutate())}
            className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {showForm && tab === "material" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <input
            value={materialForm.bezeichnung}
            onChange={(e) => setMaterialForm({ ...materialForm, bezeichnung: e.target.value })}
            placeholder="Bezeichnung"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Einheit</label>
              <input
                value={materialForm.einheit}
                onChange={(e) => setMaterialForm({ ...materialForm, einheit: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">
                Einzelpreis (EUR, optional)
              </label>
              <input
                type="number"
                step="0.01"
                value={materialForm.einzelpreis}
                onChange={(e) => setMaterialForm({ ...materialForm, einzelpreis: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Anfangsbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.menge}
                onChange={(e) => setMaterialForm({ ...materialForm, menge: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">Mindestbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.mindestbestand}
                onChange={(e) => setMaterialForm({ ...materialForm, mindestbestand: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">
                Standard-Lieferant (optional)
              </label>
              <select
                value={materialForm.lieferantId}
                onChange={(e) => setMaterialForm({ ...materialForm, lieferantId: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
              <label className="mb-1 block text-xs text-slate-500 dark:text-stone-400">
                Lagerort für Anfangsbestand
              </label>
              <select
                value={materialForm.lagerId}
                onChange={(e) => setMaterialForm({ ...materialForm, lagerId: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
            className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {tab === "kunden" && (
        <div className="space-y-2">
          {(kunden ?? []).length > 0 && (
            <input
              value={kundenSuche}
              onChange={(e) => setKundenSuche(e.target.value)}
              placeholder="Suche nach Name oder Kundennummer…"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          )}
          {kundenLoading ? (
            <SkeletonList count={3} />
          ) : (kunden ?? []).length === 0 ? (
            <EmptyState icon={Users} text="Keine Kunden vorhanden." />
          ) : kundenGefiltert.length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-stone-500">
              Keine Kunden gefunden für „{kundenSuche}“.
            </p>
          ) : (
            // Eigener scrollbarer Bereich statt die ganze Seite runterzuscrollen
            // -- Suchfeld/Tabs bleiben oben fixiert sichtbar.
            <div className="max-h-[65vh] space-y-2 overflow-y-auto pr-0.5">
              {kundenGefiltert.map((k) => (
                <button
                  key={k.id}
                  onClick={() => navigate(`/kunden/${k.id}`)}
                  className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
                >
                  <div>
                    <div className="text-xs text-slate-400 dark:text-stone-500">{k.kundennummer}</div>
                    <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{k.name}</div>
                  </div>
                  {k.typ && (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                      {k.typ}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "angebote" && (
        <div className="space-y-2">
          {angeboteLoading ? (
            <SkeletonList count={3} />
          ) : (angebote ?? []).length === 0 ? (
            <EmptyState icon={FileText} text="Keine Angebote vorhanden." />
          ) : (
            angebote!.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/angebote/${a.id}`)}
                className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">{a.angebotsnummer}</div>
                  <div className="text-sm font-medium text-slate-800 dark:text-stone-100">
                    {nameFuer(a.kunde_id)}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-stone-400">{a.gesamt_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                  {ANGEBOT_STATUS_LABEL[a.status]}
                </span>
              </button>
            ))
          )}
        </div>
      )}

      {tab === "rechnungen" && (
        <div className="space-y-2">
          {rechnungenLoading ? (
            <SkeletonList count={3} />
          ) : (rechnungen ?? []).length === 0 ? (
            <EmptyState icon={Receipt} text="Keine Rechnungen vorhanden." />
          ) : (
            rechnungen!.map((r) => (
              <button
                key={r.id}
                onClick={() => navigate(`/rechnungen/${r.id}`)}
                className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">{r.rechnungsnummer}</div>
                  <div className="text-sm font-medium text-slate-800 dark:text-stone-100">
                    {nameFuer(r.kunde_id)}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-stone-400">{r.betrag_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                  {RECHNUNG_STATUS_LABEL[r.status]}
                </span>
              </button>
            ))
          )}
        </div>
      )}

      {tab === "material" && (
        <div className="space-y-2">
          <LagerorteVerwaltung lagerorte={lagerorte.filter((l) => l.objekttyp !== "lager" || l.bezeichnung !== "Zentrallager")} />

          {(material ?? []).length > 0 && (
            <div className="space-y-2 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
              <input
                value={matSuche}
                onChange={(e) => setMatSuche(e.target.value)}
                placeholder="Suche nach Bezeichnung oder Artikelnummer…"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={matFilterLieferantId}
                  onChange={(e) => setMatFilterLieferantId(e.target.value)}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                >
                  <option value="">Alle Tags</option>
                  {(materialTags ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      #{t.label}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-stone-300">
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
            <p className="text-center text-sm text-slate-400 dark:text-stone-500">Kein Material entspricht dem Filter.</p>
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
          <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Lieferanten</h2>
              <button
                onClick={() => setShowLieferantForm((v) => !v)}
                className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
              >
                {showLieferantForm ? "Abbrechen" : "+ Neu"}
              </button>
            </div>
            {showLieferantForm && (
              <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
                <input
                  value={lieferantName}
                  onChange={(e) => setLieferantName(e.target.value)}
                  placeholder="Name"
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <input
                  value={lieferantEmail}
                  onChange={(e) => setLieferantEmail(e.target.value)}
                  placeholder="E-Mail (optional)"
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <button
                  disabled={!lieferantName.trim() || createLieferantMutation.isPending}
                  onClick={() => createLieferantMutation.mutate()}
                  className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  Anlegen
                </button>
              </div>
            )}
            {(lieferanten ?? []).length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-stone-500">Noch keine Lieferanten angelegt.</p>
            ) : (
              <div className="space-y-1">
                {lieferanten!.map((l) => (
                  <div
                    key={l.id}
                    className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
                  >
                    <div>
                      <span className="text-slate-700 dark:text-stone-200">{l.name}</span>
                      {l.email && <span className="ml-2 text-xs text-slate-400 dark:text-stone-500">{l.email}</span>}
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

          <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Offene Materialbedarfe</h2>
            <div className="mb-2 flex gap-2 rounded-md bg-slate-100 p-1 dark:bg-stone-800">
              <button
                onClick={() => setBedarfZweck("bestellung")}
                className={`btn-touch flex-1 rounded-md py-1.5 text-xs font-medium ${
                  bedarfZweck === "bestellung"
                    ? "bg-white text-slate-800 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                    : "text-slate-500 dark:text-stone-400"
                }`}
              >
                Zur Bestellung
              </button>
              <button
                onClick={() => setBedarfZweck("angebot")}
                className={`btn-touch flex-1 rounded-md py-1.5 text-xs font-medium ${
                  bedarfZweck === "angebot"
                    ? "bg-white text-slate-800 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                    : "text-slate-500 dark:text-stone-400"
                }`}
              >
                Für Angebot
              </button>
            </div>

            {(offeneBedarfe ?? []).length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-stone-500">Keine offenen Materialbedarfe.</p>
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
                    <span className="flex-1 text-slate-700 dark:text-stone-200">
                      {b.menge} {b.material_einheit} {b.material_bezeichnung}
                      <span className="ml-1.5 text-xs text-slate-400 dark:text-stone-500">
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
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                  className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
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
                  className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  Angebot aus {ausgewaehlteBedarfe.size} Position(en) erstellen
                </button>
              </div>
            )}
          </div>

          <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Bestellungen</h2>
            {(bestellungen ?? []).length === 0 ? (
              <p className="text-sm text-slate-400 dark:text-stone-500">Noch keine Bestellungen vorhanden.</p>
            ) : (
              <div className="space-y-1">
                {bestellungen!.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => navigate(`/bestellungen/${b.id}`)}
                    className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm dark:bg-stone-800"
                  >
                    <span className="text-slate-700 dark:text-stone-200">{b.bestellnummer}</span>
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
