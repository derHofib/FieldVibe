import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, X } from "lucide-react";
import { useState } from "react";

import { mailApi } from "../../api/endpoints";

export type ComposeModus =
  | { art: "neu"; accountId: string }
  | { art: "antworten"; messageId: string; an: string[]; betreff: string }
  | { art: "weiterleiten"; messageId: string; betreff: string };

interface Props {
  modus: ComposeModus;
  onGesendet: () => void;
  onAbbrechen: () => void;
}

function parseAdressen(wert: string): string[] {
  return wert
    .split(/[,;]/)
    .map((a) => a.trim())
    .filter(Boolean);
}

/** Ein Formular fuer alle drei Versandwege (Neu/Antworten/Weiterleiten) --
 * der Server entscheidet nichts ueber die Empfaenger, das macht bewusst der
 * Client (siehe Backend-Kommentar in schemas/mail_message.py), damit
 * "Antworten" und "Allen antworten" dieselbe Route nutzen koennen. */
export function ComposePanel({ modus, onGesendet, onAbbrechen }: Props) {
  const queryClient = useQueryClient();
  const [an, setAn] = useState(modus.art === "antworten" ? modus.an.join(", ") : "");
  const [cc, setCc] = useState("");
  const [bcc, setBcc] = useState("");
  const [betreff, setBetreff] = useState(modus.art !== "neu" ? modus.betreff : "");
  const [text, setText] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const senden = useMutation({
    mutationFn: async () => {
      const anListe = parseAdressen(an);
      if (modus.art === "neu") {
        await mailApi.senden(modus.accountId, {
          an: anListe,
          cc: parseAdressen(cc),
          bcc: parseAdressen(bcc),
          betreff,
          text,
        });
      } else if (modus.art === "antworten") {
        await mailApi.antworten(modus.messageId, { an: anListe, cc: parseAdressen(cc), text });
      } else {
        await mailApi.weiterleiten(modus.messageId, { an: anListe, text });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-messages"] });
      onGesendet();
    },
    onError: (err: Error) => setFehler(err.message),
  });

  const titel =
    modus.art === "neu" ? "Neue Nachricht" : modus.art === "antworten" ? "Antworten" : "Weiterleiten";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5 dark:border-stone-800">
        <p className="text-sm font-semibold text-ind-ink">{titel}</p>
        <button
          onClick={onAbbrechen}
          aria-label="Schließen"
          className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
        >
          <X size={15} strokeWidth={2} />
        </button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        <input
          value={an}
          onChange={(e) => setAn(e.target.value)}
          placeholder="An (mehrere durch Komma trennen)"
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        {modus.art !== "weiterleiten" && (
          <input
            value={cc}
            onChange={(e) => setCc(e.target.value)}
            placeholder="Cc (optional)"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        )}
        {modus.art === "neu" && (
          <input
            value={bcc}
            onChange={(e) => setBcc(e.target.value)}
            placeholder="Bcc (optional)"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        )}
        {modus.art === "neu" && (
          <input
            value={betreff}
            onChange={(e) => setBetreff(e.target.value)}
            placeholder="Betreff"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Nachricht…"
          rows={12}
          className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        {fehler && (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {fehler}
          </p>
        )}
      </div>

      <div className="flex justify-end border-t border-slate-200 p-3 dark:border-stone-800">
        <button
          onClick={() => {
            setFehler(null);
            senden.mutate();
          }}
          disabled={!parseAdressen(an).length || (modus.art === "neu" && !betreff.trim()) || senden.isPending}
          className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
        >
          {senden.isPending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} strokeWidth={2.25} />}
          Senden
        </button>
      </div>
    </div>
  );
}
