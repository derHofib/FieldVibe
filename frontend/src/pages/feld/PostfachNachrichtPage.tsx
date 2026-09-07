import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Reply } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { mailApi } from "../../api/endpoints";
import { ComposePanel } from "../../office/postfach/ComposePanel";

/** Zeigt entweder eine bestehende Nachricht (inkl. "Antworten" -- kein
 * "Allen antworten"/Weiterleiten auf dem Handy, siehe PHASE_10) oder, bei
 * id === "neu", das Compose-Formular fuer eine neue Nachricht. Beides in
 * einer Datei, weil beide Zustaende dieselbe Route "/postfach/:id" mit
 * demselben Zurueck-Verhalten teilen -- eine zweite Route fuer "neu" waere
 * nur ein Alias mit doppeltem Navigations-Code. */
export function PostfachNachrichtPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [antwortenOffen, setAntwortenOffen] = useState(false);

  const { data: accounts } = useQuery({
    queryKey: ["mail-accounts"],
    queryFn: () => mailApi.accounts.list(),
    enabled: id === "neu",
  });

  const { data: detail } = useQuery({
    queryKey: ["mail-message", id],
    queryFn: () => mailApi.message(id!),
    enabled: id !== "neu" && !!id,
  });

  const alsGelesenMutation = useMutation({
    mutationFn: (messageId: string) => mailApi.setGelesen(messageId, true),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mail-messages"] }),
  });

  useEffect(() => {
    if (detail && !detail.gelesen) {
      alsGelesenMutation.mutate(detail.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id]);

  if (id === "neu") {
    if (!accounts?.[0]) return null;
    return (
      <div className="-mx-4 h-[calc(100vh-8rem)]">
        <ComposePanel
          modus={{ art: "neu", accountId: accounts[0].id }}
          onGesendet={() => navigate("/postfach")}
          onAbbrechen={() => navigate("/postfach")}
        />
      </div>
    );
  }

  if (!detail) {
    return <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>;
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate("/postfach")} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div>
        <h1 className="text-lg font-bold text-ind-ink">
          {detail.betreff || "(kein Betreff)"}
        </h1>
        <p className="mt-1 text-xs text-ind-ink-3">
          Von{" "}
          <span className="font-medium text-ind-ink">
            {detail.von_name || detail.von_adresse}
          </span>
        </p>
      </div>

      {detail.anhaenge.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {detail.anhaenge.map((a) => (
            <button
              key={a.id}
              onClick={async () => {
                const { url } = await mailApi.attachmentUrl(detail.id, a.id);
                window.open(url, "_blank", "noopener,noreferrer");
              }}
              className="btn-touch rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 dark:border-stone-700 dark:text-stone-300"
            >
              {a.dateiname}
            </button>
          ))}
        </div>
      )}

      <p className="text-sm whitespace-pre-wrap text-ind-ink">{detail.body_text}</p>

      {antwortenOffen ? (
        <div className="-mx-4 border-t border-slate-100 pt-3 dark:border-stone-800">
          <ComposePanel
            modus={{
              art: "antworten",
              messageId: detail.id,
              an: detail.von_adresse ? [detail.von_adresse] : [],
              betreff: detail.betreff,
            }}
            onGesendet={() => navigate("/postfach")}
            onAbbrechen={() => setAntwortenOffen(false)}
          />
        </div>
      ) : (
        <button
          onClick={() => setAntwortenOffen(true)}
          className="btn-touch btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white"
        >
          <Reply size={13} strokeWidth={2} /> Antworten
        </button>
      )}
    </div>
  );
}
