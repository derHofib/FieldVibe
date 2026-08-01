import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { angeboteApi, anlagenApi, kundenApi, materialApi, rechnungenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { Anlage, AnlagenObjekttyp, AngebotStatus, Material, RechnungStatus } from "../../types";

type GeschaeftTab = "kunden" | "angebote" | "rechnungen" | "material";

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

function MaterialZeile({ material, lagerorte }: { material: Material; lagerorte: Anlage[] }) {
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
    <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{material.bezeichnung}</div>
          <div
            className={`text-xs ${
              istUnterbestand(material)
                ? "font-semibold text-red-600 dark:text-red-400"
                : "text-slate-500 dark:text-slate-400"
            }`}
          >
            Gesamt: {material.bestand_gesamt} {material.einheit} (Mindestbestand {material.mindestbestand})
          </div>
          {material.einzelpreis && (
            <div className="text-xs text-slate-400 dark:text-slate-500">{material.einzelpreis} EUR/Einheit</div>
          )}
        </div>
        {lagerorte.length > 1 && (
          <button
            onClick={() => setZeigeUmlagern((v) => !v)}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            {zeigeUmlagern ? "Abbrechen" : "Umlagern"}
          </button>
        )}
      </div>

      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 dark:border-slate-800">
        {material.bestaende.map((b) => (
          <div key={b.lager_id} className="flex items-center justify-between text-xs">
            <span className="text-slate-600 dark:text-slate-300">{b.lager_bezeichnung}</span>
            {editingLagerId === b.lager_id ? (
              <span className="flex items-center gap-1">
                <input
                  type="number"
                  step="0.01"
                  value={neueMenge}
                  onChange={(e) => setNeueMenge(e.target.value)}
                  className="w-16 rounded border border-slate-300 px-1 py-0.5 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
                <button
                  onClick={() => bestandSetzenMutation.mutate(b.lager_id)}
                  disabled={bestandSetzenMutation.isPending}
                  className="btn-touch rounded bg-gradient-to-r from-cyan-500 to-blue-600 px-2 py-0.5 text-white"
                >
                  ✓
                </button>
                <button
                  onClick={() => setEditingLagerId(null)}
                  className="btn-touch text-slate-400 dark:text-slate-500"
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
                className="btn-touch font-medium text-slate-700 underline-offset-2 hover:underline dark:text-slate-300"
              >
                {b.menge} {material.einheit}
              </button>
            )}
          </div>
        ))}
      </div>

      {zeigeUmlagern && (
        <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={umlagernVon}
              onChange={(e) => setUmlagernVon(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
              className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
              className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <button
              disabled={
                !umlagernVon || !umlagernNach || umlagernVon === umlagernNach || !umlagernMenge || umlagernMutation.isPending
              }
              onClick={() => umlagernMutation.mutate()}
              className="btn-touch shrink-0 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
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
    <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Fahrzeuge & Lagerorte</h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
        >
          {showForm ? "Abbrechen" : "+ Neu"}
        </button>
      </div>

      {lagerorte.length === 0 ? (
        <p className="mt-2 text-sm text-slate-400 dark:text-slate-500">Noch keine weiteren Lagerorte.</p>
      ) : (
        <div className="mt-2 space-y-1">
          {lagerorte.map((l) => (
            <button
              key={l.id}
              onClick={() => navigate(`/anlagen/${l.id}`)}
              className="btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm dark:bg-slate-800"
            >
              <span className="text-slate-700 dark:text-slate-200">{l.bezeichnung}</span>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                {OBJEKTTYP_LABEL[l.objekttyp]}
              </span>
            </button>
          ))}
        </div>
      )}

      {showForm && (
        <div className="mt-2 space-y-2 border-t border-slate-100 pt-2 dark:border-slate-800">
          <input
            value={bezeichnung}
            onChange={(e) => setBezeichnung(e.target.value)}
            placeholder="Bezeichnung (z.B. Transporter VW)"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <select
            value={objekttyp}
            onChange={(e) => setObjekttyp(e.target.value as AnlagenObjekttyp)}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="fahrzeug">Fahrzeug</option>
            <option value="lager">Lager</option>
            <option value="baustelle">Baustelle</option>
          </select>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Jedes Fahrzeug/Lager ist automatisch ein eigener Lagerort für Material -- keine Kunde-
            Zuordnung nötig.
          </p>
          <button
            disabled={!bezeichnung || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}
    </div>
  );
}

export function GeschaeftPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sichtbareTabs: GeschaeftTab[] = [
    ...(istModulAktiv(currentUser, "kundenverwaltung") ? (["kunden"] as const) : []),
    ...(istModulAktiv(currentUser, "abrechnung") ? (["angebote", "rechnungen"] as const) : []),
    ...(istModulAktiv(currentUser, "material") ? (["material"] as const) : []),
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
  });

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const materialAktiv = istModulAktiv(currentUser, "material");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: angebote } = useQuery({
    queryKey: ["angebote"],
    queryFn: () => angeboteApi.list(),
    enabled: abrechnungAktiv,
  });
  const { data: rechnungen } = useQuery({
    queryKey: ["rechnungen"],
    queryFn: () => rechnungenApi.list(),
    enabled: abrechnungAktiv,
  });
  const { data: material } = useQuery({
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

  const createAngebotMutation = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate(`/angebote/${angebot.id}`);
    },
  });

  const createRechnungMutation = useMutation({
    mutationFn: () => rechnungenApi.create({ kunde_id: kundeId, betrag_netto: betragNetto }),
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
      }),
    onSuccess: () => {
      setShowForm(false);
      setMaterialForm({ bezeichnung: "", einheit: "Stk", menge: "0", lagerId: "", mindestbestand: "0", einzelpreis: "" });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  if (currentUser && currentUser.role === "techniker") return <Navigate to="/feed" replace />;
  if (sichtbareTabs.length === 0) return <Navigate to="/feed" replace />;

  const nameFuer = (kundeId: string) => kunden?.find((k) => k.id === kundeId)?.name ?? "—";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Geschäft</h1>
        {istModulAktiv(currentUser, "kundenportal") && (
          <button
            onClick={() => navigate("/anfragen")}
            className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            Auftragsanfragen
          </button>
        )}
      </div>

      <div className="flex gap-2 rounded-lg bg-white p-1 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        {sichtbareTabs.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setShowForm(false);
            }}
            className={`btn-touch flex-1 rounded-md py-2 text-sm font-medium capitalize ${
              tab === t
                ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300"
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

      {showForm && tab === "kunden" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Name *</label>
            <input
              autoFocus
              value={neuerKunde.name}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, name: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                Kundennummer (optional)
              </label>
              <input
                value={neuerKunde.kundennummer}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, kundennummer: e.target.value })}
                placeholder="wird sonst vergeben"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Typ</label>
              <select
                value={neuerKunde.typ}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, typ: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Straße + Hausnr.</label>
            <input
              value={neuerKunde.strasse}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, strasse: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">PLZ</label>
              <input
                value={neuerKunde.plz}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, plz: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Ort</label>
              <input
                value={neuerKunde.ort}
                onChange={(e) => setNeuerKunde({ ...neuerKunde, ort: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Notiz</label>
            <textarea
              value={neuerKunde.notiz}
              onChange={(e) => setNeuerKunde({ ...neuerKunde, notiz: e.target.value })}
              rows={2}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Ansprechpartner können anschließend auf der Kunden-Detailseite angelegt werden.
          </p>
          <button
            disabled={!neuerKunde.name.trim() || createKundeMutation.isPending}
            onClick={() => createKundeMutation.mutate()}
            className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {showForm && tab !== "material" && tab !== "kunden" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Kunde</label>
            <select
              value={kundeId}
              onChange={(e) => setKundeId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                Betrag netto (EUR)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={betragNetto}
                onChange={(e) => setBetragNetto(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          )}
          <button
            disabled={
              !kundeId ||
              (tab === "rechnungen" && !betragNetto) ||
              createAngebotMutation.isPending ||
              createRechnungMutation.isPending
            }
            onClick={() => (tab === "angebote" ? createAngebotMutation.mutate() : createRechnungMutation.mutate())}
            className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {showForm && tab === "material" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <input
            value={materialForm.bezeichnung}
            onChange={(e) => setMaterialForm({ ...materialForm, bezeichnung: e.target.value })}
            placeholder="Bezeichnung"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Einheit</label>
              <input
                value={materialForm.einheit}
                onChange={(e) => setMaterialForm({ ...materialForm, einheit: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                Einzelpreis (EUR, optional)
              </label>
              <input
                type="number"
                step="0.01"
                value={materialForm.einzelpreis}
                onChange={(e) => setMaterialForm({ ...materialForm, einzelpreis: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Anfangsbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.menge}
                onChange={(e) => setMaterialForm({ ...materialForm, menge: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Mindestbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.mindestbestand}
                onChange={(e) => setMaterialForm({ ...materialForm, mindestbestand: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
                Lagerort für Anfangsbestand
              </label>
              <select
                value={materialForm.lagerId}
                onChange={(e) => setMaterialForm({ ...materialForm, lagerId: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
            className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {tab === "kunden" && (
        <div className="space-y-2">
          {(kunden ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-slate-500">Keine Kunden vorhanden.</p>
          ) : (
            kunden!.map((k) => (
              <button
                key={k.id}
                onClick={() => navigate(`/kunden/${k.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">{k.kundennummer}</div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{k.name}</div>
                </div>
                {k.typ && (
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {k.typ}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      )}

      {tab === "angebote" && (
        <div className="space-y-2">
          {(angebote ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-slate-500">Keine Angebote vorhanden.</p>
          ) : (
            angebote!.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/angebote/${a.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">{a.angebotsnummer}</div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {nameFuer(a.kunde_id)}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{a.gesamt_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {ANGEBOT_STATUS_LABEL[a.status]}
                </span>
              </button>
            ))
          )}
        </div>
      )}

      {tab === "rechnungen" && (
        <div className="space-y-2">
          {(rechnungen ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-slate-500">Keine Rechnungen vorhanden.</p>
          ) : (
            rechnungen!.map((r) => (
              <button
                key={r.id}
                onClick={() => navigate(`/rechnungen/${r.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">{r.rechnungsnummer}</div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {nameFuer(r.kunde_id)}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{r.betrag_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
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
          {(material ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400 dark:text-slate-500">Kein Material erfasst.</p>
          ) : (
            material!.map((m) => <MaterialZeile key={m.id} material={m} lagerorte={lagerorte} />)
          )}
        </div>
      )}
    </div>
  );
}
