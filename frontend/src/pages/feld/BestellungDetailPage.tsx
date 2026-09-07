import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { bestellungenApi, lieferantenApi } from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { useAuth } from "../../context/AuthContext";
import { downloadBlob } from "../../utils/download";
import { openPdfBlob } from "../../utils/pdf";
import type { BestellungStatus } from "../../types";

const STATUS_LABEL: Record<BestellungStatus, string> = {
  entwurf: "Entwurf",
  bestellt: "Bestellt",
  eingegangen: "Eingegangen",
};

export function BestellungDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannLoeschen = currentUser?.role === "loesch_operativ";

  const deleteMutation = useMutation({
    mutationFn: () => bestellungenApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bestellungen"] });
      navigate("/material");
    },
  });

  const { data: bestellung } = useQuery({
    queryKey: ["bestellung", id],
    queryFn: () => bestellungenApi.get(id!),
    enabled: !!id,
  });
  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });

  // Preis-Korrektur beim Wareneingang: der bisherige einzelpreis war nur die
  // Planung zum Bestellzeitpunkt (siehe BestellungPosition-Docstring im
  // Backend) -- hier kann er auf den tatsaechlich bezahlten Preis
  // angepasst werden, bevor der Wareneingang gebucht wird.
  const [wareneingangOffen, setWareneingangOffen] = useState(false);
  const [preise, setPreise] = useState<Record<string, string>>({});

  const statusMutation = useMutation({
    mutationFn: (vars: { status: BestellungStatus; positionen_preise?: Record<string, string> }) =>
      bestellungenApi.update(id!, vars),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bestellung", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe"] });
      setWareneingangOffen(false);
    },
  });

  const csvMutation = useMutation({
    mutationFn: () => bestellungenApi.csv(id!),
    onSuccess: (blob) => downloadBlob(blob, `${bestellung?.bestellnummer ?? "Bestellung"}.csv`),
  });

  const pdfMutation = useMutation({
    mutationFn: () => bestellungenApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  if (!bestellung) return <p className="text-center text-ind-ink-3">Lädt…</p>;

  const lieferant = lieferanten?.find((l) => l.id === bestellung.lieferant_id);
  const gesamtRichtwert = bestellung.positionen.reduce(
    (sum, p) => sum + Number(p.menge) * Number(p.einzelpreis),
    0,
  );

  const wareneingangOeffnen = () => {
    const initial: Record<string, string> = {};
    bestellung.positionen.forEach((p) => {
      initial[p.id] = p.einzelpreis;
    });
    setPreise(initial);
    setWareneingangOffen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Bestellung wirklich löschen? Sie wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Bestellung löschen
          </button>
        )}
      </div>

      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-ind-ink-3">{bestellung.bestellnummer}</div>
            <h1 className="text-lg font-bold text-ind-ink">
              {lieferant?.name ?? "Kein Lieferant hinterlegt"}
            </h1>
          </div>
          <span className="border border-ind-line px-2 py-1 text-xs font-semibold text-ind-ink-2">
            {STATUS_LABEL[bestellung.status]}
          </span>
        </div>
        {bestellung.notiz && (
          <p className="mt-2 text-sm text-ind-ink-2">{bestellung.notiz}</p>
        )}
        <div className="mt-3 text-right text-sm text-ind-ink-3">
          Richtwert gesamt: {gesamtRichtwert.toFixed(2)} EUR
        </div>

        <div className="mt-3 flex gap-2">
          <button
            onClick={() => csvMutation.mutate()}
            disabled={csvMutation.isPending}
            className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            <Download size={14} strokeWidth={2} /> CSV
          </button>
          <button
            onClick={() => pdfMutation.mutate()}
            disabled={pdfMutation.isPending}
            className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            <FileText size={14} strokeWidth={2} /> PDF
          </button>
        </div>
      </div>

      <div className="border border-ind-line bg-ind-bg p-4">
        <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">Positionen</h2>
        <div className="space-y-1.5">
          {bestellung.positionen.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
            >
              <div>
                <div className="text-ind-ink-2">{p.beschreibung}</div>
                <div className="text-xs text-ind-ink-3">
                  {p.menge} {p.einheit} × {p.einzelpreis} EUR (Richtwert)
                </div>
              </div>
              <div className="font-medium text-ind-ink-2">
                {(Number(p.menge) * Number(p.einzelpreis)).toFixed(2)} EUR
              </div>
            </div>
          ))}
        </div>
      </div>

      <EmailSection
        queryKey={["bestellung-emails", id]}
        listEmails={() => bestellungenApi.emails(id!)}
        sendEmail={(body) => bestellungenApi.sendEmail(id!, body)}
        defaultEmpfaenger={lieferant?.email ?? undefined}
        betreffPflicht={false}
        hinweis="Die Bestellung wird als PDF-Anhang mitgesendet."
      />

      {wareneingangOffen && (
        <div className="border border-ind-line bg-ind-bg p-4">
          <h2 className="mb-1 text-sm font-semibold text-ind-ink-3">
            Wareneingang -- Preise prüfen
          </h2>
          <p className="mb-3 text-xs text-ind-ink-3">
            Der bisherige Preis war nur ein Richtwert zum Bestellzeitpunkt. Bei Abweichung hier
            den tatsächlich bezahlten Preis eintragen.
          </p>
          <div className="space-y-1.5">
            {bestellung.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between gap-3 border border-ind-line-2 p-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-ind-ink-2">{p.beschreibung}</div>
                  <div className="text-xs text-ind-ink-3">
                    {p.menge} {p.einheit}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    inputMode="decimal"
                    value={preise[p.id] ?? p.einzelpreis}
                    onChange={(e) => setPreise((prev) => ({ ...prev, [p.id]: e.target.value }))}
                    className="w-20 rounded-md border border-slate-200 px-2 py-1 text-right text-sm dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
                  />
                  <span className="text-xs text-ind-ink-3">EUR</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => setWareneingangOffen(false)}
              disabled={statusMutation.isPending}
              className="btn-touch flex-1 rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
            >
              Abbrechen
            </button>
            <button
              onClick={() => statusMutation.mutate({ status: "eingegangen", positionen_preise: preise })}
              disabled={statusMutation.isPending}
              className="btn-touch flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Wareneingang jetzt buchen
            </button>
          </div>
        </div>
      )}
      {!wareneingangOffen && bestellung.status === "entwurf" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate({ status: "bestellt" })}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Als bestellt markieren
          </button>
          <button
            onClick={wareneingangOeffnen}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            Wareneingang buchen
          </button>
        </div>
      )}
      {!wareneingangOffen && bestellung.status === "bestellt" && (
        <button
          onClick={wareneingangOeffnen}
          disabled={statusMutation.isPending}
          className="btn-touch w-full rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Wareneingang buchen
        </button>
      )}
      {bestellung.status === "eingegangen" && (
        <p className="text-center text-sm text-ind-ink-3">
          Wareneingang gebucht -- Bestand wurde entsprechend erhöht.
        </p>
      )}
    </div>
  );
}
