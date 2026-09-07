import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Briefcase, ShieldAlert } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { partnerApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnsprechpartnerVerwaltung } from "../../components/AnsprechpartnerVerwaltung";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { Adresse, PartnerFreigabeStatus, PartnerNachweisTyp } from "../../types";

const NACHWEIS_TYP_LABEL: Record<PartnerNachweisTyp, string> = {
  freistellungsbescheinigung: "Freistellungsbescheinigung (§48 EStG)",
  haftpflichtversicherung: "Haftpflichtversicherung",
  gewerbeanmeldung: "Gewerbeanmeldung",
  handwerksrolle: "Eintrag Handwerksrolle",
  avv_dsgvo: "AVV (DSGVO)",
  sonstiges: "Sonstiges",
};

const FREIGABE_LABEL: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "Wartet auf Rückmeldung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const FREIGABE_FARBE: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  angenommen: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  abgelehnt: "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400",
};

function leereAdresse(adresse: Adresse | null): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

function Stammdaten({ partnerId }: { partnerId: string }) {
  const queryClient = useQueryClient();
  const { data: partner } = useQuery({
    queryKey: ["partner", partnerId],
    queryFn: () => partnerApi.get(partnerId),
  });
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState({
    gewerk: "",
    telefon: "",
    email: "",
    strasse: "",
    plz: "",
    ort: "",
    notiz: "",
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      partnerApi.update(partnerId, {
        gewerk: form.gewerk || null,
        telefon: form.telefon || null,
        email: form.email || null,
        adresse:
          form.strasse || form.plz || form.ort
            ? { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined }
            : null,
        notiz: form.notiz || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["partner", partnerId] });
      setBearbeiten(false);
    },
  });

  const aktivMutation = useMutation({
    mutationFn: () => partnerApi.update(partnerId, { aktiv: !partner?.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["partner", partnerId] }),
  });

  if (!partner) return null;

  if (!bearbeiten) {
    const adressZeile = [partner.adresse?.strasse, [partner.adresse?.plz, partner.adresse?.ort].filter(Boolean).join(" ")]
      .filter(Boolean)
      .join(", ");
    return (
      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ind-ink-3">Stammdaten</h2>
          <button
            onClick={() => {
              setForm({
                gewerk: partner.gewerk ?? "",
                telefon: partner.telefon ?? "",
                email: partner.email ?? "",
                ...leereAdresse(partner.adresse),
                notiz: partner.notiz ?? "",
              });
              setBearbeiten(true);
            }}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            Bearbeiten
          </button>
        </div>
        <dl className="space-y-1 text-sm">
          <div className="flex justify-between gap-2">
            <dt className="text-ind-ink-3">Gewerk</dt>
            <dd className="text-right text-ind-ink-2">
              {partner.gewerk || <span className="text-ind-ink-3">nicht hinterlegt</span>}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-ind-ink-3">Telefon</dt>
            <dd className="text-right text-ind-ink-2">{partner.telefon || "—"}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-ind-ink-3">E-Mail</dt>
            <dd className="text-right text-ind-ink-2">{partner.email || "—"}</dd>
          </div>
        </dl>
        {adressZeile && <p className="mt-2 text-sm text-ind-ink-2">{adressZeile}</p>}
        {partner.notiz && <p className="mt-2 text-sm text-ind-ink-3">{partner.notiz}</p>}
        <button
          onClick={() => aktivMutation.mutate()}
          disabled={aktivMutation.isPending}
          className="btn-touch mt-3 btn-industry btn-industry-secondary px-3 py-1.5 text-xs font-semibold"
        >
          {partner.aktiv ? "Deaktivieren" : "Aktivieren"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2 border border-ind-line bg-ind-bg p-4">
      <h2 className="text-sm font-semibold text-ind-ink-3">Stammdaten bearbeiten</h2>
      <input
        value={form.gewerk}
        onChange={(e) => setForm({ ...form, gewerk: e.target.value })}
        placeholder="Gewerk / was die Firma macht"
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <input
        value={form.telefon}
        onChange={(e) => setForm({ ...form, telefon: e.target.value })}
        placeholder="Telefon"
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <input
        type="email"
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
        placeholder="E-Mail"
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
      </div>
      <textarea
        value={form.notiz}
        onChange={(e) => setForm({ ...form, notiz: e.target.value })}
        placeholder="Notiz"
        rows={2}
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function NeuerNachweis({ partnerId }: { partnerId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [typ, setTyp] = useState<PartnerNachweisTyp>("freistellungsbescheinigung");
  const [gueltigBis, setGueltigBis] = useState("");
  const [notiz, setNotiz] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      partnerApi.nachweisAnlegen(partnerId, {
        typ,
        gueltig_bis: gueltigBis || undefined,
        notiz: notiz || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["partner-nachweise", partnerId] });
      setZeigen(false);
      setGueltigBis("");
      setNotiz("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Nachweis konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-blue-700 underline dark:text-blue-400">
        + Nachweis hinterlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border border-ind-line-2 p-3">
      <select
        value={typ}
        onChange={(e) => setTyp(e.target.value as PartnerNachweisTyp)}
        className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
      >
        {Object.entries(NACHWEIS_TYP_LABEL).map(([wert, label]) => (
          <option key={wert} value={wert}>
            {label}
          </option>
        ))}
      </select>
      <div>
        <label className="mb-1 block text-xs text-ind-ink-3">Gültig bis (optional)</label>
        <input
          type="date"
          value={gueltigBis}
          onChange={(e) => setGueltigBis(e.target.value)}
          className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
        />
      </div>
      <input
        value={notiz}
        onChange={(e) => setNotiz(e.target.value)}
        placeholder="Notiz (optional)"
        className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
      />
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function NachweiseVerwaltung({ partnerId, kannVerwalten }: { partnerId: string; kannVerwalten: boolean }) {
  const queryClient = useQueryClient();
  const { data: nachweise } = useQuery({
    queryKey: ["partner-nachweise", partnerId],
    queryFn: () => partnerApi.nachweise(partnerId),
  });

  const removeMutation = useMutation({
    mutationFn: (nachweisId: string) => partnerApi.nachweisEntfernen(partnerId, nachweisId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["partner-nachweise", partnerId] }),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ nachweisId, file }: { nachweisId: string; file: File }) =>
      partnerApi.nachweisHochladen(partnerId, nachweisId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["partner-nachweise", partnerId] }),
  });

  async function herunterladen(nachweisId: string) {
    const { url } = await partnerApi.nachweisUrl(partnerId, nachweisId);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  const abgelaufeneAnzahl = (nachweise ?? []).filter((n) => n.abgelaufen).length;

  return (
    <div className="border border-ind-line bg-ind-bg p-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ind-ink-3">Nachweise</h2>
        {abgelaufeneAnzahl > 0 && (
          <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-500/10 dark:text-red-400">
            <ShieldAlert size={12} strokeWidth={2} /> {abgelaufeneAnzahl} abgelaufen
          </span>
        )}
      </div>
      {(nachweise ?? []).length === 0 ? (
        <p className="text-sm text-ind-ink-3">Keine Nachweise hinterlegt.</p>
      ) : (
        <div className="mb-2 space-y-2">
          {nachweise!.map((n) => (
            <div
              key={n.id}
              className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm dark:bg-stone-800/60"
            >
              <div className="min-w-0">
                <div className="font-medium text-ind-ink">{NACHWEIS_TYP_LABEL[n.typ]}</div>
                <div className="text-xs text-ind-ink-3">
                  {n.gueltig_bis
                    ? `Gültig bis ${new Date(n.gueltig_bis).toLocaleDateString("de-DE")}`
                    : "Ohne Ablaufdatum"}
                  {n.abgelaufen && (
                    <span className="ml-1.5 font-semibold text-red-600 dark:text-red-400">· abgelaufen</span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {n.dokument_s3_key && (
                  <button
                    onClick={() => herunterladen(n.id)}
                    className="btn-touch text-xs text-cyan-700 dark:text-cyan-400"
                  >
                    Herunterladen
                  </button>
                )}
                {kannVerwalten && (
                  <label className="btn-touch cursor-pointer text-xs text-slate-500 hover:text-ind-ink-2 dark:hover:text-stone-200">
                    {n.dokument_s3_key ? "Ersetzen" : "Hochladen"}
                    <input
                      type="file"
                      className="hidden"
                      disabled={uploadMutation.isPending}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadMutation.mutate({ nachweisId: n.id, file });
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
                {kannVerwalten && (
                  <button
                    onClick={() => removeMutation.mutate(n.id)}
                    disabled={removeMutation.isPending}
                    className="btn-touch text-xs text-red-700 dark:text-red-400"
                  >
                    Entfernen
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {kannVerwalten && <NeuerNachweis partnerId={partnerId} />}
    </div>
  );
}

function ZugewieseneVorgaenge({ partnerId }: { partnerId: string }) {
  const navigate = useNavigate();
  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge", "partner", partnerId],
    queryFn: () => vorgaengeApi.list({ partner_id: partnerId }),
  });

  if (!vorgaenge || vorgaenge.length === 0) return null;

  return (
    <div className="border border-ind-line bg-ind-bg p-4">
      <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">Zugewiesene Vorgänge</h2>
      <div className="space-y-2">
        {vorgaenge.map((v) => (
          <button
            key={v.id}
            onClick={() => navigate(`/vorgaenge/${v.id}`)}
            className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-slate-50 p-3 text-left dark:bg-stone-800/60"
          >
            <div>
              <div className="text-xs text-ind-ink-3">{v.vorgangsnummer}</div>
              <div className="text-sm font-medium text-ind-ink">{v.titel}</div>
            </div>
            {v.partner_freigabe_status && (
              <span
                className={`rounded-full px-2 py-1 text-xs font-semibold ${FREIGABE_FARBE[v.partner_freigabe_status]}`}
              >
                {FREIGABE_LABEL[v.partner_freigabe_status]}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export function PartnerProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: partner, isLoading } = useQuery({
    queryKey: ["partner", id],
    queryFn: () => partnerApi.get(id!),
    enabled: !!id,
  });
  const kannVerwalten = hatRecht("partner", "bearbeiten");

  const deleteMutation = useMutation({
    mutationFn: () => partnerApi.remove(id!),
    onSuccess: () => navigate("/partner"),
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  if (!istModulAktiv(currentUser, "nachunternehmer")) return null;
  if (isLoading || !partner) return <p className="text-center text-ind-ink-3">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Briefcase size={18} strokeWidth={2} className="text-ind-ink-3" />
            <div>
              <h1 className="text-lg font-bold text-ind-ink">{partner.name}</h1>
              {partner.gewerk && (
                <p className="text-sm text-ind-ink-3">{partner.gewerk}</p>
              )}
            </div>
          </div>
          <button
            onClick={() => {
              if (window.confirm(`${partner.name} wirklich löschen?`)) deleteMutation.mutate();
            }}
            className="btn-touch rounded-md bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20"
          >
            Löschen
          </button>
        </div>
        {deleteError && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{deleteError}</p>}
      </div>

      <Stammdaten partnerId={id!} />
      <AnsprechpartnerVerwaltung
        liste={partner.ansprechpartner}
        kannVerwalten={kannVerwalten}
        onSpeichern={async (naechsteListe) => {
          await partnerApi.update(id!, { ansprechpartner: naechsteListe });
          queryClient.invalidateQueries({ queryKey: ["partner", id] });
        }}
      />
      <NachweiseVerwaltung partnerId={id!} kannVerwalten={kannVerwalten} />
      <ZugewieseneVorgaenge partnerId={id!} />
    </div>
  );
}
