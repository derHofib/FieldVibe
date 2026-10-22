import { useQueryClient } from "@tanstack/react-query";
import { Camera, Eye, EyeOff, Paperclip, PenLine } from "lucide-react";
import { useLocation } from "react-router-dom";
import { ApiError } from "../../../api/client";
import { vorgaengeApi } from "../../../api/endpoints";
import { EmailSection } from "../../../components/EmailSection";
import { SignaturePad } from "../../../components/SignaturePad";
import { discardOutboxItem } from "../../../offline/outbox";
import type { Kunde, UserAuswahl } from "../../../types";
import { EmailBubble, EventBubble, OutboxBubble } from "./VerlaufBlasen";
import type { PartnerDaten } from "./useVorgangPartner";
import type { VerlaufDaten } from "./useVorgangVerlauf";

interface VerlaufInhaltProps {
  id: string | undefined;
  kunde: Kunde | undefined;
  users: UserAuswahl[] | undefined;
  partnerDaten: PartnerDaten;
  verlaufDaten: VerlaufDaten;
}

/** Verlauf-Ansicht: im dichten Layout ein Tab (breit: feste zweite Spalte), im kompakten Layout die Unterseite /vorgaenge/:id/verlauf. */
export function VerlaufInhalt({ id, kunde, users, partnerDaten, verlaufDaten }: VerlaufInhaltProps) {
  const { partnerKommentarMoeglich, zugewiesenerPartner } = partnerDaten;
  const {
    anPartner, comment, commentMutation, dokumentInputRef, dokumentMutation,
    eigeneOutboxItemsGefiltert, fileInputRef, fotoMutation, highlightMutation, kundenansicht,
    kundensichtbar, setAnPartner, setComment, setKundenansicht, setKundensichtbar,
    setShowMentionPicker, setShowUnterschriftPad, setVerlaufFilter, showMentionPicker,
    showUnterschriftPad, unterschriftMutation, verlaufEintraegeGefiltert, verlaufFilter,
  } = verlaufDaten;
  const queryClient = useQueryClient();
  const location = useLocation();
  return (
    <>
      <EmailSection
        queryKey={["vorgang-emails", id]}
        listEmails={() => vorgaengeApi.emails(id!)}
        sendEmail={(body) =>
          vorgaengeApi.sendEmail(id!, {
            empfaenger: body.empfaenger,
            betreff: body.betreff ?? "",
            inhalt: body.inhalt ?? "",
          })
        }
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        showHistory={false}
        defaultOpen={location.hash === "#email"}
      />

      <div className="scroll-mt-4 flex items-center justify-between gap-2">
        <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Verlauf</h2>
        <span className="text-sm text-label2">{kundenansicht ? "Kundenansicht" : "Interne Ansicht"}</span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch border px-3 py-1 text-xs font-semibold ${
            kundenansicht ? "border-tint bg-tint-solid text-white" : "border-sep text-label hover:bg-fill"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div className="mt-2 mb-1 flex flex-wrap items-center gap-1.5 text-xs">
        {(
          [
            { wert: "alle", label: "Alle" },
            { wert: "kommentare", label: "Kommentare" },
            { wert: "system", label: "System" },
            { wert: "email", label: "E-Mail" },
          ] as const
        ).map((f) => (
          <button
            key={f.wert}
            onClick={() => setVerlaufFilter(f.wert)}
            className={`btn-touch border px-2.5 py-1 font-medium ${
              verlaufFilter === f.wert
                ? "border-tint bg-tint-solid text-white"
                : "border-sep text-label2 hover:bg-fill"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div>
        {verlaufEintraegeGefiltert.length === 0 && eigeneOutboxItemsGefiltert.length === 0 ? (
          <p className="text-center text-sm text-label2">
            {verlaufFilter === "alle" ? "Noch keine Einträge." : "Keine Einträge in diesem Filter."}
          </p>
        ) : (
          <>
            {/* Noch nicht synchronisierte Einträge sind immer die neuesten
                -- stehen deshalb vor den bereits synchronisierten Events. */}
            {!kundenansicht &&
              eigeneOutboxItemsGefiltert.map((item) => (
                <OutboxBubble
                  key={item.client_uuid}
                  item={item}
                  onDiscard={async (clientUuid) => {
                    await discardOutboxItem(clientUuid);
                    queryClient.invalidateQueries({ queryKey: ["outbox", id] });
                  }}
                />
              ))}
            {verlaufEintraegeGefiltert.map((eintrag) =>
              eintrag.art === "email" ? (
                <EmailBubble key={`email-${eintrag.email.id}`} email={eintrag.email} />
              ) : (
                <EventBubble
                  key={`event-${eintrag.event.id}`}
                  event={eintrag.event}
                  onHighlight={(eventId) => highlightMutation.mutate(eventId)}
                />
              ),
            )}
          </>
        )}
      </div>

      {!kundenansicht && (
        <div className="sticky bottom-[var(--klebe-abstand)] space-y-2 card-ap p-3">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none border border-sep bg-transparent p-2 text-sm text-label"
            />
            {/* .card-ap bringt schon eine eigene box-shadow mit (siehe
             * Cascade-Layer-Falle in DESIGN.md) -- shadow-lg hier waere
             * tot, deshalb nicht ergaenzt. */}
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto card-ap">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm text-label hover:bg-fill"
                  >
                    {u.name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) fotoMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <input
            ref={dokumentInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) dokumentMutation.mutate(file);
              e.target.value = "";
            }}
          />
          {partnerKommentarMoeglich && (
            <label className="mb-2 flex items-center gap-2 text-sm text-label2">
              <input
                type="checkbox"
                checked={anPartner}
                onChange={(e) => setAnPartner(e.target.checked)}
                className="h-4 w-4 accent-tint"
              />
              Auch an Partner {zugewiesenerPartner?.name ?? ""}
            </label>
          )}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setShowMentionPicker((v) => !v)}
                title="Erwähnen"
                aria-label="Erwähnen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-base text-label hover:bg-fill"
              >
                @
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fotoMutation.isPending}
                title="Foto anhängen"
                aria-label="Foto anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill disabled:opacity-50"
              >
                <Camera size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => dokumentInputRef.current?.click()}
                disabled={dokumentMutation.isPending}
                title="Dokument anhängen"
                aria-label="Dokument anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill disabled:opacity-50"
              >
                <Paperclip size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => setShowUnterschriftPad((v) => !v)}
                title="Unterschrift erfassen"
                aria-label="Unterschrift erfassen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill"
              >
                <PenLine size={16} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => setKundensichtbar((v) => !v)}
                title={
                  kundensichtbar
                    ? "Für Kunde sichtbar – antippen zum Verbergen"
                    : "Nur intern – antippen um für Kunde sichtbar zu machen"
                }
                aria-label="Für Kunde sichtbar umschalten"
                aria-pressed={kundensichtbar}
                className={`btn-touch flex h-9 w-9 items-center justify-center border ${
                  kundensichtbar ? "border-tint text-tint" : "border-sep text-label2 hover:bg-fill"
                }`}
              >
                {kundensichtbar ? <Eye size={16} strokeWidth={2} /> : <EyeOff size={16} strokeWidth={2} />}
              </button>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch btn-ap-primary shrink-0 px-4 py-2 text-sm"
            >
              Senden
            </button>
          </div>

          {showUnterschriftPad && (
            <div className="mt-2">
              <SignaturePad
                isSaving={unterschriftMutation.isPending}
                onCancel={() => setShowUnterschriftPad(false)}
                onSave={(blob, unterzeichnerName) => unterschriftMutation.mutate({ blob, unterzeichnerName })}
              />
              {unterschriftMutation.isError && (
                <p className="mt-1 text-xs text-st-fehlt">
                  {unterschriftMutation.error instanceof ApiError
                    ? unterschriftMutation.error.message
                    : "Unterschrift konnte nicht gespeichert werden — bitte erneut versuchen."}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
