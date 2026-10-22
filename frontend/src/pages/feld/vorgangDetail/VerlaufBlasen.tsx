import { AlertTriangle, Camera, Clock, FileText, Mail, Paperclip, Star } from "lucide-react";
import { MentionText } from "../../../components/MentionText";
import type { OutboxItem } from "../../../offline/db";
import type { EmailLog, VorgangEvent } from "../../../types";
import { EVENT_LABEL } from "./konstanten";

// Unauffaellige, transparente Pill zur Unterscheidung der Eintragsart im
// gemeinsamen Verlauf (Kommentar/E-Mail laufen dort jetzt durcheinander) --
// bewusst zurueckhaltend statt eines vollflaechigen Badges, siehe
// Design-Vorschlag "Feed und Detail neu gedacht".
export function VerlaufTypTag({ children }: { children: string }) {
  return (
    <span className="border border-sep px-1.5 py-0.5 text-[10px] font-medium text-label2">
      {children}
    </span>
  );
}

export function EventBubble({
  event,
  onHighlight,
}: {
  event: VorgangEvent;
  onHighlight: (eventId: number) => void;
}) {
  if (event.is_system || event.event_type === "status_change") {
    const label =
      event.event_type === "status_change"
        ? `Status: ${(event.payload as { von?: string }).von ?? "?"} → ${(event.payload as { nach?: string }).nach ?? "?"}`
        : event.body ?? EVENT_LABEL[event.event_type] ?? event.event_type;
    return (
      <div className="my-2 text-center text-xs text-label2">
        {label} · {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 card-ap p-3">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-label2">
        <div className="flex items-center gap-1.5">
          <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          {event.event_type === "kommentar" && <VerlaufTypTag>Kommentar</VerlaufTypTag>}
        </div>
        <div className="flex items-center gap-1.5">
          {event.partner_sichtbar && event.author_user_id !== null && (
            <span className="border border-tint px-2 py-0.5 text-tint">Partner sieht das</span>
          )}
          {event.kundensichtbar && (
            <span className="border border-tint px-2 py-0.5 text-tint">
              Kundensichtbar
            </span>
          )}
        </div>
      </div>
      {event.event_type === "foto" && event.foto_url && (
        <>
          <a href={event.foto_url} target="_blank" rel="noreferrer">
            <img
              src={event.foto_thumbnail_url ?? event.foto_url}
              alt="Foto"
              className="mb-2 max-h-64 rounded-md object-cover"
            />
          </a>
          <button
            onClick={() => onHighlight(event.id)}
            className="btn-touch mb-2 flex items-center gap-1 text-xs font-medium text-st-arbeit"
          >
            <Star size={13} strokeWidth={2} /> Als Highlight markieren
          </button>
        </>
      )}
      {event.event_type === "unterschrift" && event.unterschrift_url && (
        <div className="mb-2">
          <img
            src={event.unterschrift_url}
            alt="Unterschrift"
            className="max-h-32 border border-sep bg-white"
          />
          {typeof event.payload.unterzeichner_name === "string" && (
            <p className="mt-1 text-xs text-label2">
              Unterschrieben von: {event.payload.unterzeichner_name}
            </p>
          )}
        </div>
      )}
      {event.event_type === "dokument" && event.dokument_url && (
        <a
          href={event.dokument_url}
          target="_blank"
          rel="noreferrer"
          className="btn-touch mb-2 flex items-center gap-2 border border-sep px-3 py-2 text-sm text-label hover:bg-fill"
        >
          <Paperclip size={15} strokeWidth={2} />
          {event.dokument_dateiname ?? "Dokument"}
        </a>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap break-words text-sm text-label">
          <MentionText text={event.body} />
        </p>
      )}
    </div>
  );
}

// E-Mails werden nicht mehr in einer separaten Box gefuehrt, sondern im
// gemeinsamen Verlauf mit den Kommentaren gemischt (siehe Design-Vorschlag
// "Feed und Detail neu gedacht") -- gleiche Bubble-Optik wie EventBubble,
// nur mit Betreff/Empfaenger statt Freitext-Body.
export function EmailBubble({ email }: { email: EmailLog }) {
  return (
    <div className="mb-3 card-ap p-3">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-label2">
        <div className="flex items-center gap-1.5">
          <span>{new Date(email.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          <VerlaufTypTag>E-Mail</VerlaufTypTag>
        </div>
        {email.status === "fehler" && (
          <span className="border border-st-fehlt px-2 py-0.5 text-st-fehlt">
            Fehler
          </span>
        )}
      </div>
      <div className="mb-1 flex items-start gap-1.5 text-sm text-label">
        <Mail size={14} strokeWidth={2} className="mt-0.5 shrink-0 text-label2" />
        <div>
          <span className="font-medium">{email.betreff || "(ohne Betreff)"}</span>
          <span className="text-label2"> · an {email.empfaenger}</span>
        </div>
      </div>
      {email.status === "fehler" && email.fehlermeldung && (
        <p className="text-xs text-st-fehlt">{email.fehlermeldung}</p>
      )}
    </div>
  );
}

export function OutboxBubble({
  item,
  onDiscard,
}: {
  item: OutboxItem;
  onDiscard: (clientUuid: string) => void;
}) {
  return (
    <div
      className={`mb-3 rounded-lg border border-dashed p-3 ${
        item.failed
          ? "border-st-fehlt bg-st-fehlt-bg"
          : "border-sepstrong"
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-1 text-xs">
        {item.failed ? (
          <span className="flex items-center gap-1 text-st-fehlt">
            <AlertTriangle size={13} strokeWidth={2} /> Vom Server abgelehnt{item.errorMessage ? `: ${item.errorMessage}` : ""}
          </span>
        ) : (
          <span className="flex items-center gap-1 text-label2">
            <Clock size={13} strokeWidth={2} />
            <span>Nicht synchronisiert</span>
          </span>
        )}
        {item.failed && (
          <button
            onClick={() => onDiscard(item.client_uuid)}
            className="btn-touch text-st-fehlt underline"
          >
            Verwerfen
          </button>
        )}
      </div>
      {item.kind === "foto" ? (
        <p className="flex items-center gap-1 text-sm text-label">
          <Camera size={14} strokeWidth={2} /> Foto wartet auf Synchronisierung
        </p>
      ) : item.kind === "dokument" ? (
        <p className="flex items-center gap-1 text-sm text-label">
          <FileText size={14} strokeWidth={2} /> {item.dokumentName ?? "Dokument"} wartet auf Synchronisierung
        </p>
      ) : item.kind === "status" ? (
        <p className="text-sm text-label">Statusänderung zu „{item.statusValue}“ wartet auf Synchronisierung</p>
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm text-label">{item.body}</p>
      )}
    </div>
  );
}
