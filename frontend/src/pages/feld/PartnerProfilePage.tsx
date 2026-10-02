import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Briefcase, Link2, ShieldAlert } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { partnerApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnsprechpartnerVerwaltung } from "../../components/AnsprechpartnerVerwaltung";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { einladungFehlerText, partnerPortalLink, portalZugangStatus } from "../../utils/partnerZugang";
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
  vorgeschlagen: "bg-st-arbeit-bg text-st-arbeit  ",
  angenommen: "bg-st-erledigt-bg text-st-erledigt  ",
  abgelehnt: "bg-st-fehlt-bg text-st-fehlt  ",
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
      <div className="card-ap p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Stammdaten</h2>
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
            className="btn-touch text-xs font-medium text-tint "
          >
            Bearbeiten
          </button>
        </div>
        <dl className="space-y-1 text-sm">
          <div className="flex justify-between gap-2">
            <dt className="text-label2">Gewerk</dt>
            <dd className="text-right text-label">
              {partner.gewerk || <span className="text-label2">nicht hinterlegt</span>}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-label2">Telefon</dt>
            <dd className="text-right text-label">{partner.telefon || "—"}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-label2">E-Mail</dt>
            <dd className="text-right text-label">{partner.email || "—"}</dd>
          </div>
        </dl>
        {adressZeile && <p className="mt-2 text-sm text-label">{adressZeile}</p>}
        {partner.notiz && <p className="mt-2 text-sm text-label2">{partner.notiz}</p>}
        <button
          onClick={() => aktivMutation.mutate()}
          disabled={aktivMutation.isPending}
          className="btn-touch mt-3 btn-ap px-3 py-1.5 text-xs font-semibold"
        >
          {partner.aktiv ? "Deaktivieren" : "Aktivieren"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2 card-ap p-4">
      <h2 className="text-sm font-semibold text-label2">Stammdaten bearbeiten</h2>
      <input
        value={form.gewerk}
        onChange={(e) => setForm({ ...form, gewerk: e.target.value })}
        placeholder="Gewerk / was die Firma macht"
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <input
        value={form.telefon}
        onChange={(e) => setForm({ ...form, telefon: e.target.value })}
        placeholder="Telefon"
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <input
        type="email"
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
        placeholder="E-Mail"
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
        />
      </div>
      <textarea
        value={form.notiz}
        onChange={(e) => setForm({ ...form, notiz: e.target.value })}
        placeholder="Notiz"
        rows={2}
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-sep py-2 text-sm font-medium text-label "
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
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-tint underline ">
        + Nachweis hinterlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border border-sepstrong p-3">
      <select
        value={typ}
        onChange={(e) => setTyp(e.target.value as PartnerNachweisTyp)}
        className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
      >
        {Object.entries(NACHWEIS_TYP_LABEL).map(([wert, label]) => (
          <option key={wert} value={wert}>
            {label}
          </option>
        ))}
      </select>
      <div>
        <label className="mb-1 block text-xs text-label2">Gültig bis (optional)</label>
        <input
          type="date"
          value={gueltigBis}
          onChange={(e) => setGueltigBis(e.target.value)}
          className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
        />
      </div>
      <input
        value={notiz}
        onChange={(e) => setNotiz(e.target.value)}
        placeholder="Notiz (optional)"
        className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
      />
      {error && <p className="text-sm text-st-fehlt ">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-sep py-2 text-sm font-medium text-label "
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
    <div className="card-ap p-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-label2">Nachweise</h2>
        {abgelaufeneAnzahl > 0 && (
          <span className="flex items-center gap-1 rounded-full bg-st-fehlt-bg px-2 py-0.5 text-xs font-semibold text-st-fehlt ">
            <ShieldAlert size={12} strokeWidth={2} /> {abgelaufeneAnzahl} abgelaufen
          </span>
        )}
      </div>
      {(nachweise ?? []).length === 0 ? (
        <p className="text-sm text-label2">Keine Nachweise hinterlegt.</p>
      ) : (
        <div className="mb-2 space-y-2">
          {nachweise!.map((n) => (
            <div
              key={n.id}
              className="flex items-center justify-between gap-2 rounded-md bg-fill px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <div className="font-medium text-label">{NACHWEIS_TYP_LABEL[n.typ]}</div>
                <div className="text-xs text-label2">
                  {n.gueltig_bis
                    ? `Gültig bis ${new Date(n.gueltig_bis).toLocaleDateString("de-DE")}`
                    : "Ohne Ablaufdatum"}
                  {n.abgelaufen && (
                    <span className="ml-1.5 font-semibold text-st-fehlt ">· abgelaufen</span>
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
                  <label className="btn-touch cursor-pointer text-xs text-label2 hover:text-label dark:hover:text-label3">
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
                    className="btn-touch text-xs text-st-fehlt "
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

function datumKurz(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" });
}

function PortalZugang({ partnerId, partnerEmail }: { partnerId: string; partnerEmail: string | null }) {
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const [formOffen, setFormOffen] = useState(false);
  const [email, setEmail] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [kopiert, setKopiert] = useState(false);

  const { data: zugaenge } = useQuery({
    queryKey: ["partner-zugaenge", partnerId],
    queryFn: () => partnerApi.zugaenge(partnerId),
  });
  const { data: einladungen } = useQuery({
    queryKey: ["partner-einladungen", partnerId],
    queryFn: () => partnerApi.einladungen(partnerId),
  });

  function neuLaden() {
    void queryClient.invalidateQueries({ queryKey: ["partner-zugaenge", partnerId] });
    void queryClient.invalidateQueries({ queryKey: ["partner-einladungen", partnerId] });
  }
  function bei(err: unknown) {
    setFehler(
      err instanceof ApiError
        ? einladungFehlerText(err.status, err.message)
        : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
    );
  }

  const einladen = useMutation({
    mutationFn: () => partnerApi.einladen(partnerId, email.trim()),
    onSuccess: () => {
      setFehler(null);
      setFormOffen(false);
      neuLaden();
    },
    onError: bei,
  });
  const erneut = useMutation({
    mutationFn: (einladungId: string) => partnerApi.einladungErneutSenden(partnerId, einladungId),
    onSuccess: () => {
      setFehler(null);
      neuLaden();
    },
    onError: bei,
  });
  const widerrufen = useMutation({
    mutationFn: (einladungId: string) => partnerApi.einladungWiderrufen(partnerId, einladungId),
    onSuccess: () => {
      setFehler(null);
      neuLaden();
    },
    onError: bei,
  });
  const sperren = useMutation({
    mutationFn: (v: { zugangId: string; aktiv: boolean }) =>
      partnerApi.zugangAktivSetzen(partnerId, v.zugangId, v.aktiv),
    onSuccess: () => {
      setFehler(null);
      neuLaden();
    },
    onError: bei,
  });

  if (!zugaenge || !einladungen) return null;
  const status = portalZugangStatus(zugaenge, einladungen);
  const kannEinladen = hatRecht("partner", "erstellen");
  const kannWiderrufen = hatRecht("partner", "loeschen");
  const kannSperren = hatRecht("partner", "bearbeiten");
  const arbeitet = einladen.isPending || erneut.isPending || widerrufen.isPending || sperren.isPending;
  const portalLink = partnerPortalLink(window.location.origin);

  const einladungKopf = status.art === "offen" || status.art === "abgelaufen" ? status.einladung : null;

  return (
    <div className="card-ap p-4">
      <h2 className="mb-2 text-sm font-semibold text-label2">Portal-Zugang</h2>

      {status.art === "keiner" && <p className="text-sm text-label">Kein Zugang eingerichtet.</p>}
      {(status.art === "aktiv" || status.art === "gesperrt") && (
        <div className="text-sm">
          <p className="text-label">
            <span
              className={`mr-2 rounded-full px-2 py-0.5 text-xs font-semibold ${
                status.art === "aktiv" ? "bg-st-erledigt-bg text-st-erledigt" : "bg-st-fehlt-bg text-st-fehlt"
              }`}
            >
              {status.art === "aktiv" ? "Aktiv" : "Gesperrt"}
            </span>
            seit {datumKurz(status.zugang.created_at)}
          </p>
          <p className="mt-1 break-all text-label2">
            {status.zugang.name} · {status.zugang.email}
          </p>
        </div>
      )}
      {einladungKopf && (
        <div className="text-sm">
          <p className="text-label">
            <span className="mr-2 rounded-full bg-st-arbeit-bg px-2 py-0.5 text-xs font-semibold text-st-arbeit">
              {status.art === "abgelaufen" ? "Einladung abgelaufen" : "Einladung offen"}
            </span>
            seit {datumKurz(einladungKopf.created_at)}
          </p>
          <p className="mt-1 break-all text-label2">{einladungKopf.email}</p>
        </div>
      )}

      {fehler && (
        <p role="alert" className="mt-3 rounded-md bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          {fehler}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {einladungKopf && kannEinladen && (
          <button
            onClick={() => erneut.mutate(einladungKopf.id)}
            disabled={arbeitet}
            className="btn-touch btn-ap px-3 py-1.5 text-xs font-semibold"
          >
            Einladung erneut senden
          </button>
        )}
        {einladungKopf?.registrierungslink && (
          <button
            onClick={async () => {
              await navigator.clipboard.writeText(einladungKopf.registrierungslink!);
              setKopiert(true);
              setTimeout(() => setKopiert(false), 1500);
            }}
            className="btn-touch btn-ap px-3 py-1.5 text-xs font-semibold"
          >
            {kopiert ? "Kopiert ✓" : "Link kopieren"}
          </button>
        )}
        {einladungKopf && kannWiderrufen && (
          <button
            onClick={() => {
              if (window.confirm(`Einladung an ${einladungKopf.email} widerrufen?`)) widerrufen.mutate(einladungKopf.id);
            }}
            disabled={arbeitet}
            className="btn-touch rounded-md bg-st-fehlt-bg px-3 py-1.5 text-xs font-semibold text-st-fehlt"
          >
            Einladung widerrufen
          </button>
        )}
        {(status.art === "aktiv" || status.art === "gesperrt") && kannSperren && (
          <button
            onClick={() => {
              if (
                status.art === "gesperrt" ||
                window.confirm("Zugang sperren? Der Partner kann sich danach nicht mehr anmelden.")
              ) {
                sperren.mutate({ zugangId: status.zugang.id, aktiv: status.art === "gesperrt" });
              }
            }}
            disabled={arbeitet}
            className="btn-touch btn-ap px-3 py-1.5 text-xs font-semibold"
          >
            {status.art === "gesperrt" ? "Zugang entsperren" : "Zugang sperren"}
          </button>
        )}
        {(status.art === "keiner" || status.art === "abgelaufen") && kannEinladen && !formOffen && (
          <button
            onClick={() => {
              setEmail(partnerEmail ?? "");
              setFormOffen(true);
            }}
            className="btn-touch btn-ap-primary rounded-md px-3 py-1.5 text-xs font-semibold"
          >
            Zugang einladen
          </button>
        )}
      </div>

      {formOffen && (
        <form
          className="mt-3 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            setFehler(null);
            einladen.mutate();
          }}
        >
          <label htmlFor="partner-einladung-email" className="block text-xs text-label2">
            E-Mail-Adresse des Partners
          </label>
          <input
            id="partner-einladung-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-sm text-label"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={einladen.isPending || !email.trim()}
              className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
            >
              Einladung senden
            </button>
            <button
              type="button"
              onClick={() => setFormOffen(false)}
              className="btn-touch flex-1 rounded-md border border-sep py-2 text-sm font-medium text-label"
            >
              Abbrechen
            </button>
          </div>
        </form>
      )}

      <p className="mt-3 flex items-start gap-1.5 text-xs text-label2">
        <Link2 size={13} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          Der Partner meldet sich im Partnerportal an:{" "}
          <span className="font-medium break-all text-label">{portalLink}</span>
        </span>
      </p>
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
    <div className="card-ap p-4">
      <h2 className="mb-2 text-sm font-semibold text-label2">Zugewiesene Vorgänge</h2>
      <div className="space-y-2">
        {vorgaenge.map((v) => (
          <button
            key={v.id}
            onClick={() => navigate(`/vorgaenge/${v.id}`)}
            className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-fill p-3 text-left"
          >
            <div>
              <div className="text-xs text-label2">{v.vorgangsnummer}</div>
              <div className="text-sm font-medium text-label">{v.titel}</div>
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
  if (isLoading || !partner) return <p className="text-center text-label2">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Briefcase size={18} strokeWidth={2} className="text-label2" />
            <div>
              <h1 className="text-lg font-bold text-label">{partner.name}</h1>
              {partner.gewerk && (
                <p className="text-sm text-label2">{partner.gewerk}</p>
              )}
            </div>
          </div>
          <button
            onClick={() => {
              if (window.confirm(`${partner.name} wirklich löschen?`)) deleteMutation.mutate();
            }}
            className="btn-touch rounded-md bg-st-fehlt-bg px-3 py-1.5 text-xs font-semibold text-st-fehlt hover:bg-st-fehlt-bg dark:hover:bg-st-fehlt-dot"
          >
            Löschen
          </button>
        </div>
        {deleteError && <p className="mt-2 text-sm text-st-fehlt ">{deleteError}</p>}
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
      <PortalZugang partnerId={id!} partnerEmail={partner.email} />
      <NachweiseVerwaltung partnerId={id!} kannVerwalten={kannVerwalten} />
      <ZugewieseneVorgaenge partnerId={id!} />
    </div>
  );
}
