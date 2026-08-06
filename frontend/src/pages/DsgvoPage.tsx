import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dsgvoApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { DsgvoDokument, DsgvoDokumentTyp } from "../types";

// Muss mit DSGVO_DOKUMENT_TYPEN in backend/app/models/dsgvo_dokument.py
// uebereinstimmen.
const DOKUMENT_LABEL: Record<DsgvoDokumentTyp, string> = {
  avv_vorlage: "Auftragsverarbeitungsvertrag (Vorlage)",
  datenschutzerklaerung: "Datenschutzerklärung",
  impressum: "Impressum",
  loeschkonzept: "Löschkonzept",
  tom_dokument: "TOM-Dokument (Technische und organisatorische Maßnahmen)",
  meldeprozess: "Meldeprozess Datenschutzverletzungen",
  verzeichnis_verarbeitungstaetigkeiten: "Verzeichnis von Verarbeitungstätigkeiten",
};
const ALLE_TYPEN = Object.keys(DOKUMENT_LABEL) as DsgvoDokumentTyp[];

function formatGroesse(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DokumentKarte({ typ, dokument }: { typ: DsgvoDokumentTyp; dokument?: DsgvoDokument }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => dsgvoApi.upload(typ, file),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["dsgvo-dokumente"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Upload fehlgeschlagen"),
  });

  const removeMutation = useMutation({
    mutationFn: () => dsgvoApi.remove(typ),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["dsgvo-dokumente"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  async function handleDownload() {
    try {
      const { url } = await dsgvoApi.downloadUrl(typ);
      window.open(url, "_blank");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Download fehlgeschlagen");
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="font-medium text-slate-800 dark:text-slate-100">{DOKUMENT_LABEL[typ]}</div>
          {dokument ? (
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {dokument.dateiname} · {formatGroesse(dokument.groesse_bytes)} · hochgeladen am{" "}
              {new Date(dokument.updated_at).toLocaleDateString("de-DE")}
            </div>
          ) : (
            <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">Noch kein Dokument hochgeladen</div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {dokument && (
            <>
              <button
                onClick={handleDownload}
                className="btn-touch rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Herunterladen
              </button>
              <button
                onClick={() => {
                  if (window.confirm(`"${DOKUMENT_LABEL[typ]}" wirklich löschen?`)) removeMutation.mutate();
                }}
                disabled={removeMutation.isPending}
                className="btn-touch rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:text-red-400 dark:hover:bg-red-500/10"
              >
                Löschen
              </button>
            </>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
          >
            {uploadMutation.isPending ? "Lädt hoch…" : dokument ? "Ersetzen" : "Hochladen"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{error}</p>}
    </div>
  );
}

export function DsgvoPage() {
  const { data: dokumente } = useQuery({
    queryKey: ["dsgvo-dokumente"],
    queryFn: dsgvoApi.list,
  });

  const dokumentByTyp = new Map(dokumente?.map((d) => [d.typ, d]));

  return (
    <div className="max-w-2xl space-y-4">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Zentrale Ablage der DSGVO-Pflichtdokumente (AVV-Vorlage, Datenschutzerklärung, Impressum,
        Löschkonzept, TOM-Dokument, Meldeprozess, Verarbeitungsverzeichnis). Erlaubt sind PDF, Word
        (.doc/.docx) oder Bilddateien (max. 10 MB).
      </p>
      <div className="space-y-3">
        {ALLE_TYPEN.map((typ) => (
          <DokumentKarte key={typ} typ={typ} dokument={dokumentByTyp.get(typ)} />
        ))}
      </div>
    </div>
  );
}
