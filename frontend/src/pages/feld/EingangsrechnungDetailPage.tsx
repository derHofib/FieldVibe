import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ExternalLink, FileCode, FileText, Inbox, Paperclip, Trash2 } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { eingangsrechnungenApi, lieferantenApi } from "../../api/endpoints";
import { StatusPille } from "../../components/apple/StatusPille";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import type { Eingangsrechnung, EingangsrechnungKategorie, EingangsrechnungStatus } from "../../types";
import { BelegVorschau } from "../../components/rechnung/BelegVorschau";
import { eingangStatusToken } from "../../components/rechnung/rechnungenFilter";
import { eRechnungSyntaxLabel, hinweisZeilen } from "../../utils/eRechnung";
import { formatEuro } from "../../utils/format";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";
import { Select } from "../../components/apple/Select";
import { AktionsMenue } from "../../components/AktionsMenue";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";

const STATUS_LABEL: Record<EingangsrechnungStatus, string> = {
  entwurf: "Entwurf (E-Mail-Import)",
  offen: "Offen",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const KATEGORIE_LABEL: Record<EingangsrechnungKategorie, string> = {
  wareneinkauf: "Wareneinkauf",
  betriebskosten: "Betriebskosten",
  miete: "Miete",
  personal: "Personal",
  fahrzeug: "Fahrzeug",
  versicherung: "Versicherung",
  sonstiges: "Sonstiges",
};

/** Hinweise aus dem Import (mehrere Steuersätze, Reverse Charge, Summenabweichung, ...):
 * Vorsteuer-relevant, daher auffällig und nicht wegklickbar. */
function ImportHinweise({ hinweis }: { hinweis: string | null }) {
  const zeilen = hinweisZeilen(hinweis);
  if (zeilen.length === 0) return null;
  return (
    <Hinweiskasten ton="warnung" titel="Hinweise zum Import – bitte prüfen">
      <ul className="list-disc space-y-0.5 pl-4">
        {zeilen.map((z) => (
          <li key={z}>{z}</li>
        ))}
      </ul>
    </Hinweiskasten>
  );
}

export type EingangsrechnungLayout = "standard" | "dicht" | "vollbild";

/** Im Office-Panel (dicht) bleiben Filter und Suche der Liste in der URL stehen. */
function useZurListe(layout: EingangsrechnungLayout) {
  const navigate = useNavigate();
  const { search } = useLocation();
  return () => navigate({ pathname: "/rechnungseingang", search: layout === "dicht" ? search : "" });
}

function EntwurfBestaetigenView({
  eingangsrechnung,
  layout,
}: {
  eingangsrechnung: Eingangsrechnung;
  layout: EingangsrechnungLayout;
}) {
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const zurListe = useZurListe(layout);
  const queryClient = useQueryClient();
  const [lieferantId, setLieferantId] = useState("");
  const [lieferantName, setLieferantName] = useState(eingangsrechnung.lieferant_name);
  const [rechnungsnummer, setRechnungsnummer] = useState(eingangsrechnung.rechnungsnummer_lieferant);
  const [rechnungsdatum, setRechnungsdatum] = useState(eingangsrechnung.rechnungsdatum.slice(0, 10));
  const [betragNetto, setBetragNetto] = useState(eingangsrechnung.betrag_netto);
  const [kategorie, setKategorie] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });

  const bestaetigenMutation = useMutation({
    meta: { erfolg: "Bestätigt" },
    mutationFn: () =>
      eingangsrechnungenApi.update(eingangsrechnung.id, {
        lieferant_id: lieferantId || null,
        lieferant_name: lieferantId ? undefined : lieferantName,
        rechnungsnummer_lieferant: rechnungsnummer,
        rechnungsdatum,
        betrag_netto: betragNetto,
        kategorie: kategorie || undefined,
        status: "offen",
      }),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", eingangsrechnung.id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Bestätigen fehlgeschlagen"),
  });

  const verwerfenMutation = useMutation({
    meta: { erfolg: "Verworfen" },
    mutationFn: () => eingangsrechnungenApi.remove(eingangsrechnung.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      zurListe();
    },
  });

  const inputClass =
    "w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-fliess text-label";

  return (
    <div className="space-y-4">
      {layout === "standard" && (
        <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
          ← Zurück
        </button>
      )}
      {layout === "vollbild" && (
        <button
          onClick={() => navigate(`/rechnungseingang/${eingangsrechnung.id}`)}
          className="btn-ap inline-flex items-center gap-1 px-3 py-1.5 text-sekundaer font-medium"
        >
          <ChevronLeft size={14} strokeWidth={2} aria-hidden="true" /> Rechnungseingang
        </button>
      )}

      <div className="flex items-start gap-1.5 rounded-lg bg-st-arbeit-bg px-4 py-3 text-fliess text-st-arbeit ">
        <Inbox size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
        Per E-Mail importiert{eingangsrechnung.email_absender && ` von ${eingangsrechnung.email_absender}`}
        {eingangsrechnung.email_betreff && ` · "${eingangsrechnung.email_betreff}"`} – bitte Angaben gegen den
        Beleg prüfen und bestätigen.
      </div>
      <ImportHinweise hinweis={eingangsrechnung.import_hinweis} />

      <div className={`grid grid-cols-1 gap-4 ${layout === "dicht" ? "" : "lg:grid-cols-2"}`}>
        <div className="card-ap p-2">
          <BelegVorschau id={eingangsrechnung.id} iframeKlasse="h-[70vh] w-full rounded-md" />
        </div>

        <div className="space-y-3 card-ap p-4">
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-sekundaer text-label2">Lieferant</label>
            <Select id={`${uid}-0`} value={lieferantId} onChange={(e) => setLieferantId(e.target.value)}>
              <option value="">Name manuell eintragen…</option>
              {(lieferanten ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
          </div>
          {!lieferantId && (
            <input
              value={lieferantName}
              onChange={(e) => setLieferantName(e.target.value)}
              placeholder="Name des Ausstellers"
              className={inputClass}
            />
          )}
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-meta text-label2">Rechnungsnummer</label>
            <input id={`${uid}-1`}
              value={rechnungsnummer}
              onChange={(e) => setRechnungsnummer(e.target.value)}
              placeholder="Rechnungsnummer (vom Aussteller)"
              className={inputClass}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor={`${uid}-2`} className="mb-1 block text-meta text-label2">Rechnungsdatum</label>
              <input id={`${uid}-2`}
                type="date"
                value={rechnungsdatum}
                onChange={(e) => setRechnungsdatum(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor={`${uid}-3`} className="mb-1 block text-sekundaer text-label2">Betrag netto</label>
              <input id={`${uid}-3`}
                type="number"
                step="0.01"
                value={betragNetto}
                onChange={(e) => setBetragNetto(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label htmlFor={`${uid}-4`} className="mb-1 block text-sekundaer text-label2">Kategorie</label>
            <Select id={`${uid}-4`} value={kategorie} onChange={(e) => setKategorie(e.target.value)}>
              <option value="">Kategorie…</option>
              {Object.entries(KATEGORIE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>

          {fehler && <p className="text-sekundaer text-st-fehlt ">{fehler}</p>}

          <div className="flex gap-2 pt-2">
            <button
              disabled={!rechnungsnummer || !betragNetto || Number(betragNetto) <= 0 || bestaetigenMutation.isPending}
              onClick={() => bestaetigenMutation.mutate()}
              className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md btn-ap-primary px-3 py-2 text-sekundaer font-medium disabled:opacity-50"
            >
              <Check size={15} strokeWidth={2.25} /> Als Rechnung übernehmen
            </button>
            <button
              onClick={async () => {
                if (await bestaetigen({ titel: "Entwurf verwerfen (z.B. keine echte Rechnung)?", text: "Wandert in den Papierkorb.", bestaetigenLabel: "Verwerfen" })) {
                  verwerfenMutation.mutate();
                }
              }}
              disabled={verwerfenMutation.isPending}
              className="btn-touch rounded-md bg-fill px-3 py-2 text-sekundaer font-medium text-st-fehlt disabled:opacity-50 "
            >
              Verwerfen
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function EingangsrechnungDetailPage({
  id: idProp,
  layout = "standard",
}: {
  /** Eingebettet (Office-Panel) kommt die ID als Prop, sonst aus der Route. */
  id?: string;
  layout?: EingangsrechnungLayout;
} = {}) {
  const bestaetigen = useBestaetigung();
  const params = useParams<{ id: string }>();
  const id = idProp ?? params.id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const zurListe = useZurListe(layout);
  const { currentUser, hatRecht } = useAuth();
  const kannErstellen = hatRecht("abrechnung", "erstellen");
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
  const [showZahlungForm, setShowZahlungForm] = useState(false);
  const [zahlungBetrag, setZahlungBetrag] = useState("");

  const { data: eingangsrechnung, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["eingangsrechnung", id],
    queryFn: () => eingangsrechnungenApi.get(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => eingangsrechnungenApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      zurListe();
    },
  });

  const statusMutation = useMutation({
    meta: { erfolg: "Status geändert" },
    mutationFn: (status: string) => eingangsrechnungenApi.update(id!, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
  });

  const addPositionMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      eingangsrechnungenApi.addPosition(id!, {
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
  });

  const belegUploadMutation = useMutation({
    meta: { erfolg: "Hochgeladen" },
    mutationFn: (file: File) => eingangsrechnungenApi.belegUpload(id!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung-beleg-url", id] });
    },
  });

  const belegRemoveMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => eingangsrechnungenApi.belegRemove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung-beleg-url", id] });
    },
  });

  const belegAnzeigenMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.belegUrl(id!),
    onSuccess: (res) => {
      if (res.url) window.open(res.url, "_blank");
    },
  });

  const xmlAnzeigenMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.xmlUrl(id!),
    onSuccess: (res) => {
      if (res.url) window.open(res.url, "_blank");
    },
  });

  const addZahlungMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => eingangsrechnungenApi.addZahlung(id!, { betrag: zahlungBetrag }),
    onSuccess: () => {
      setShowZahlungForm(false);
      setZahlungBetrag("");
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
  });

  const alsBezahltMutation = useMutation({
    meta: { erfolg: "Als bezahlt markiert" },
    mutationFn: (betrag: string) => eingangsrechnungenApi.addZahlung(id!, { betrag }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
  });

  if (ladeFehler && !eingangsrechnung) return <FehlerZustand fehler={ladeFehler} was="Die Eingangsrechnung" zurueck onErneut={() => void neuLaden()} className="py-6" />;
  if (!eingangsrechnung) return <DetailSkeleton />;


  if (eingangsrechnung.status === "entwurf") {
    return <EntwurfBestaetigenView eingangsrechnung={eingangsrechnung} layout={layout} />;
  }

  const syntaxLabel = eRechnungSyntaxLabel(eingangsrechnung.e_rechnung_syntax);
  const dicht = layout !== "standard";
  const vollbild = layout === "vollbild";
  const offenerBetrag = Number(eingangsrechnung.offener_betrag);
  // Gutschriften (negativer Betrag) lassen keine Zahlung zu -- das Backend lehnt sie ab.
  const kannZahlen = eingangsrechnung.status === "offen" && offenerBetrag > 0;
  const zahlungFormOeffnen = () => {
    setZahlungBetrag(eingangsrechnung.offener_betrag);
    setShowZahlungForm(true);
  };
  const skontoAktiv = !!(eingangsrechnung.skonto_prozent && eingangsrechnung.skonto_frist);

  const menue =
    kannLoeschen && eingangsrechnung.status === "offen" ? (
      <AktionsMenue
        label="Weitere Aktionen"
        touch={!dicht}
        eintraege={[
          {
            label: "Eingangsrechnung löschen",
            icon: Trash2,
            destruktiv: true,
            disabled: deleteMutation.isPending,
            onClick: async () => {
              if (await bestaetigen({ titel: "Eingangsrechnung löschen?", text: "Sie wandert in den Papierkorb.", bestaetigenLabel: "Löschen" })) {
                deleteMutation.mutate();
              }
            },
          },
        ]}
      />
    ) : null;

  const kopfKarte = (
    <div className="card-ap p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-meta text-label2">
            {eingangsrechnung.rechnungsnummer_lieferant}
          </div>
          <h1 className="text-titel-mobil font-bold text-label">
            {eingangsrechnung.lieferant_name}
          </h1>
        </div>
        {dicht ? (
          <StatusPille
            status={eingangStatusToken(eingangsrechnung.status) ?? "neu"}
            label={STATUS_LABEL[eingangsrechnung.status]}
          />
        ) : (
          <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-1 text-sekundaer font-semibold text-label">
            {STATUS_LABEL[eingangsrechnung.status]}
          </span>
        )}
      </div>
      {syntaxLabel && (
        <div className="mt-2">
          <StatusPille status="neu" label={`E-Rechnung · ${syntaxLabel}`} />
        </div>
      )}
      <p className="mt-1 text-meta text-label2">
        Rechnungsdatum {new Date(eingangsrechnung.rechnungsdatum).toLocaleDateString("de-DE")}
      </p>
      {eingangsrechnung.faellig_am && (
        <p className="mt-1 text-meta text-label2">
          Fällig am {new Date(eingangsrechnung.faellig_am).toLocaleDateString("de-DE")}
        </p>
      )}
      {eingangsrechnung.kategorie && (
        <p className="mt-1 text-sekundaer text-label2">
          Kategorie: {KATEGORIE_LABEL[eingangsrechnung.kategorie]}
        </p>
      )}
      {eingangsrechnung.notiz && (
        <p className="mt-2 whitespace-pre-line text-fliess text-label">{eingangsrechnung.notiz}</p>
      )}
      {skontoAktiv && !vollbild && (
        <p className="mt-1 text-sekundaer font-medium text-tint">
          Skonto {eingangsrechnung.skonto_prozent}% bis {new Date(eingangsrechnung.skonto_frist!).toLocaleDateString("de-DE")}
          {" "}(Ersparnis {eingangsrechnung.skonto_betrag} EUR)
        </p>
      )}

      {dicht ? (
        <div className="mt-3 space-y-2">
          <div className={`grid gap-2 ${vollbild && skontoAktiv ? "grid-cols-3" : "grid-cols-2"}`}>
            <div className="rounded-[var(--radius-ap-md)] bg-fill p-3">
              <p className="text-meta text-label2">Brutto</p>
              <p className="ap-heading text-titel-mobil font-semibold tabular-nums text-label">
                {formatEuro(eingangsrechnung.betrag_brutto)}
              </p>
            </div>
            <div className="rounded-[var(--radius-ap-md)] bg-fill p-3">
              <p className="text-meta text-label2">Offen</p>
              <p className="ap-heading text-titel-mobil font-semibold tabular-nums text-label">
                {formatEuro(eingangsrechnung.offener_betrag)}
              </p>
            </div>
            {vollbild && skontoAktiv && (
              <div className="rounded-[var(--radius-ap-md)] bg-fill p-3">
                <p className="text-meta text-label2">
                  Skonto {eingangsrechnung.skonto_prozent}% bis {new Date(eingangsrechnung.skonto_frist!).toLocaleDateString("de-DE")}
                </p>
                <p className="ap-heading text-titel-mobil font-semibold tabular-nums text-st-erledigt">
                  {formatEuro(eingangsrechnung.skonto_betrag ?? 0)}
                </p>
              </div>
            )}
          </div>
          <p className="text-sekundaer text-label2">
            Netto {formatEuro(eingangsrechnung.betrag_netto)} · MwSt. {Number(eingangsrechnung.mwst_satz)} %
            {Number(eingangsrechnung.bezahlter_betrag) > 0 && ` · Bezahlt ${formatEuro(eingangsrechnung.bezahlter_betrag)}`}
          </p>
        </div>
      ) : (
        <div className="mt-3 text-right text-fliess">
          <div className="text-label2">Netto: {eingangsrechnung.betrag_netto} EUR</div>
          <div className="font-semibold text-label">
            Brutto: {eingangsrechnung.betrag_brutto} EUR
          </div>
          {Number(eingangsrechnung.bezahlter_betrag) > 0 && (
            <div className="text-sekundaer text-label2">
              Bezahlt: {eingangsrechnung.bezahlter_betrag} EUR · Offen: {eingangsrechnung.offener_betrag} EUR
            </div>
          )}
        </div>
      )}
    </div>
  );

  const belegKarte = (
    <div className="card-ap p-4">
      <h2 className="mb-2 text-fliess font-semibold text-label2">Beleg</h2>
      {eingangsrechnung.hat_xml && (
        <div className="mb-3 space-y-1.5">
          <button
            onClick={() => xmlAnzeigenMutation.mutate()}
            disabled={xmlAnzeigenMutation.isPending}
            className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sekundaer font-medium text-label disabled:opacity-50"
          >
            <FileCode size={14} strokeWidth={2} aria-hidden="true" /> Original-XML herunterladen
          </button>
          <p className="text-sekundaer text-label2">
            Die XML ist der Beleg und wird unverändert aufbewahrt.
            {eingangsrechnung.xml_sha256 && (
              <>
                {" "}
                Prüfsumme (SHA-256): <span className="break-all font-mono">{eingangsrechnung.xml_sha256}</span>
              </>
            )}
          </p>
        </div>
      )}
      {eingangsrechnung.beleg_object_key ? (
        <div className="flex gap-2">
          <button
            onClick={() => belegAnzeigenMutation.mutate()}
            disabled={belegAnzeigenMutation.isPending}
            className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sekundaer font-medium text-label disabled:opacity-50 "
          >
            <FileText size={14} strokeWidth={2} /> Beleg anzeigen
          </button>
          {eingangsrechnung.status === "offen" && !eingangsrechnung.hat_xml && (
            <AktionsMenue
              label="Weitere Aktionen"
              touch
              eintraege={[
                {
                  label: "Beleg entfernen",
                  icon: Trash2,
                  destruktiv: true,
                  disabled: belegRemoveMutation.isPending,
                  onClick: () => belegRemoveMutation.mutate(),
                },
              ]}
            />
          )}
        </div>
      ) : eingangsrechnung.hat_xml ? null : (
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) belegUploadMutation.mutate(file);
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={belegUploadMutation.isPending}
            className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sekundaer font-medium text-label disabled:opacity-50 "
          >
            <Paperclip size={14} strokeWidth={2} /> Beleg hochladen
          </button>
        </div>
      )}
    </div>
  );

  const belegEntfernbar =
    eingangsrechnung.beleg_object_key && eingangsrechnung.status === "offen" && !eingangsrechnung.hat_xml;

  // Ganze Seite: der Beleg steht neben den Daten, damit man Beträge und Positionen dagegen prüfen kann.
  const belegVorschauKarte = (
    <div className="card-ap p-2 xl:sticky xl:top-4 xl:self-start">
      <div className="flex flex-wrap items-center justify-between gap-2 px-2 py-1.5">
        <h2 className="text-fliess font-semibold text-label2">Beleg</h2>
        <div className="flex items-center gap-2">
          {eingangsrechnung.hat_xml && (
            <button
              onClick={() => xmlAnzeigenMutation.mutate()}
              disabled={xmlAnzeigenMutation.isPending}
              className="btn-ap inline-flex items-center gap-1 px-3 py-1 text-sekundaer font-medium disabled:opacity-50"
            >
              <FileCode size={14} strokeWidth={2} aria-hidden="true" /> XML
            </button>
          )}
          {eingangsrechnung.beleg_object_key && (
            <button
              onClick={() => belegAnzeigenMutation.mutate()}
              disabled={belegAnzeigenMutation.isPending}
              className="btn-ap inline-flex items-center gap-1 px-3 py-1 text-sekundaer font-medium disabled:opacity-50"
            >
              <ExternalLink size={14} strokeWidth={2} aria-hidden="true" /> Öffnen
            </button>
          )}
          {belegEntfernbar && (
            <AktionsMenue
              label="Beleg-Aktionen"
              eintraege={[
                {
                  label: "Beleg entfernen",
                  icon: Trash2,
                  destruktiv: true,
                  disabled: belegRemoveMutation.isPending,
                  onClick: () => belegRemoveMutation.mutate(),
                },
              ]}
            />
          )}
        </div>
      </div>
      {eingangsrechnung.beleg_object_key ? (
        <BelegVorschau id={eingangsrechnung.id} iframeKlasse="h-[calc(100vh-12rem)] w-full rounded-md" />
      ) : eingangsrechnung.hat_xml ? (
        <p className="p-4 text-sekundaer text-label2">
          Zu dieser E-Rechnung gibt es kein PDF. Die XML ist der Beleg.
        </p>
      ) : (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files?.[0];
            if (file) belegUploadMutation.mutate(file);
          }}
          className="m-2 flex min-h-[40vh] flex-col items-center justify-center gap-2 rounded-[var(--radius-ap-card)] border-2 border-dashed border-sepstrong p-6 text-center"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) belegUploadMutation.mutate(file);
            }}
          />
          <Paperclip size={28} strokeWidth={1.75} className="text-label2" aria-hidden="true" />
          <p className="text-fliess font-semibold text-label">Beleg hierher ziehen oder auswählen</p>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={belegUploadMutation.isPending}
            className="btn-ap px-4 py-1.5 text-sekundaer font-medium disabled:opacity-50"
          >
            {belegUploadMutation.isPending ? "Lädt hoch…" : "Datei auswählen"}
          </button>
        </div>
      )}
    </div>
  );

  const positionenKarte = (
    <div className="card-ap p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-fliess font-semibold text-label2">Positionen</h2>
        {eingangsrechnung.status === "offen" && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="btn-touch text-sekundaer font-medium text-tint "
          >
            {showForm ? "Abbrechen" : "+ Position"}
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-3 space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
          <input
            value={form.beschreibung}
            onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
            placeholder="Beschreibung"
            className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
          <div className="grid grid-cols-3 gap-2">
            <input
              type="number"
              step="0.01"
              value={form.menge}
              onChange={(e) => setForm({ ...form, menge: e.target.value })}
              placeholder="Menge"
              className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <input
              value={form.einheit}
              onChange={(e) => setForm({ ...form, einheit: e.target.value })}
              placeholder="Einheit"
              className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <input
              type="number"
              step="0.01"
              value={form.einzelpreis}
              onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
              placeholder="Preis"
              className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
          </div>
          <button
            disabled={!form.beschreibung || addPositionMutation.isPending}
            onClick={() => addPositionMutation.mutate()}
            className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
          >
            Hinzufügen
          </button>
        </div>
      )}

      {eingangsrechnung.positionen.length === 0 ? (
        <p className="text-sekundaer text-label2">
          Keine eigenen Positionen – Betrag wurde als Gesamtsumme angelegt.
        </p>
      ) : (
        <div className="space-y-1.5">
          {eingangsrechnung.positionen.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between rounded-md bg-fill p-2 text-fliess"
            >
              <div>
                <div className="text-label">{p.beschreibung}</div>
                <div className="text-sekundaer text-label2">
                  {p.menge} {p.einheit} × {p.einzelpreis} EUR
                </div>
              </div>
              <div className="font-medium text-label">{p.gesamt} EUR</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const zahlungenKarte = (
    <div className="card-ap p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-fliess font-semibold text-label2">Zahlungen</h2>
        {/* Gutschriften (negativer Betrag) lassen keine Zahlung zu -- das Backend lehnt sie ab. */}
        {eingangsrechnung.status === "offen" && Number(eingangsrechnung.offener_betrag) > 0 && (
          <button
            onClick={() => {
              setZahlungBetrag(eingangsrechnung.offener_betrag);
              setShowZahlungForm((v) => !v);
            }}
            className="btn-touch text-sekundaer font-medium text-tint "
          >
            {showZahlungForm ? "Abbrechen" : "+ Zahlung"}
          </button>
        )}
      </div>

      {showZahlungForm && (
        <div className="mb-3 space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
          <input
            type="number"
            step="0.01"
            value={zahlungBetrag}
            onChange={(e) => setZahlungBetrag(e.target.value)}
            placeholder="Betrag"
            className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
          {addZahlungMutation.isError && (
            <p className="text-sekundaer text-st-fehlt ">
              Zahlung übersteigt den offenen Betrag oder ist ungültig.
            </p>
          )}
          <button
            disabled={!zahlungBetrag || addZahlungMutation.isPending}
            onClick={() => addZahlungMutation.mutate()}
            className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
          >
            Zahlung erfassen
          </button>
        </div>
      )}

      {eingangsrechnung.zahlungen.length === 0 ? (
        <p className="text-sekundaer text-label2">Noch keine Zahlung erfasst.</p>
      ) : (
        <div className="space-y-1.5">
          {eingangsrechnung.zahlungen.map((z) => (
            <div
              key={z.id}
              className="flex items-center justify-between rounded-md bg-fill p-2 text-fliess"
            >
              <span className="text-label2">
                {new Date(z.datum).toLocaleDateString("de-DE")}
              </span>
              <span className="font-medium text-label">{z.betrag} EUR</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const stornoKnopf =
    eingangsrechnung.status === "offen" ? (
      <button
        onClick={async () => {
          if (await bestaetigen({ titel: "Diese Eingangsrechnung stornieren?", bestaetigenLabel: "Stornieren" })) statusMutation.mutate("storniert");
        }}
        disabled={statusMutation.isPending}
        className="btn-touch w-full rounded-md bg-fill px-4 py-2 text-sekundaer font-medium text-label disabled:opacity-50 "
      >
        Stornieren
      </button>
    ) : null;

  if (vollbild) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={() => navigate(`/rechnungseingang/${eingangsrechnung.id}`)}
            className="btn-ap inline-flex items-center gap-1 px-3 py-1.5 text-sekundaer font-medium"
          >
            <ChevronLeft size={14} strokeWidth={2} aria-hidden="true" /> Rechnungseingang
          </button>
          <div className="flex items-center gap-2">
            {kannErstellen && kannZahlen && (
              <>
                <button onClick={zahlungFormOeffnen} className="btn-ap px-4 py-1.5 text-sekundaer font-medium">
                  Zahlung erfassen
                </button>
                <button
                  disabled={alsBezahltMutation.isPending}
                  onClick={async () => {
                    if (
                      await bestaetigen({
                        titel: "Als bezahlt markieren?",
                        text: `Es wird eine Zahlung über den offenen Betrag von ${formatEuro(eingangsrechnung.offener_betrag)} mit heutigem Datum erfasst.`,
                        bestaetigenLabel: "Bezahlt",
                      })
                    ) {
                      alsBezahltMutation.mutate(eingangsrechnung.offener_betrag);
                    }
                  }}
                  className={`${NEU_BUTTON_KLASSE} disabled:opacity-50`}
                >
                  Als bezahlt markieren
                </button>
              </>
            )}
            {menue}
          </div>
        </div>

        <ImportHinweise hinweis={eingangsrechnung.import_hinweis} />

        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <div className="space-y-4">
            {kopfKarte}
            {positionenKarte}
            {zahlungenKarte}
            {stornoKnopf}
          </div>
          {belegVorschauKarte}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {dicht ? (
        menue && <div className="flex justify-end">{menue}</div>
      ) : (
        <div className="flex items-center justify-between">
          <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
            ← Zurück
          </button>
          {menue}
        </div>
      )}

      <ImportHinweise hinweis={eingangsrechnung.import_hinweis} />

      {kopfKarte}
      {belegKarte}
      {positionenKarte}
      {zahlungenKarte}
      {stornoKnopf}
    </div>
  );
}
