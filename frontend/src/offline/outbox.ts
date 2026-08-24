import { apiFetch, apiFetchForm, ApiError } from "../api/client";
import type { Vorgang, VorgangEvent } from "../types";
import { getDb, type OutboxItem } from "./db";

type Listener = () => void;
const listeners = new Set<Listener>();
function notify(): void {
  listeners.forEach((l) => l());
}

/** For components that want to re-render when the outbox changes (count
 * badges, "nicht synchronisiert" markers) without polling IndexedDB. */
export function subscribeOutbox(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function queueKommentar(
  vorgangId: string,
  body: string,
  kundensichtbar: boolean,
): Promise<string> {
  const clientUuid = crypto.randomUUID();
  const db = await getDb();
  await db.put("outbox", {
    client_uuid: clientUuid,
    vorgang_id: vorgangId,
    kind: "kommentar",
    body,
    kundensichtbar,
    created_at: new Date().toISOString(),
  });
  notify();
  return clientUuid;
}

export async function queueFoto(
  vorgangId: string,
  file: Blob,
  fotoName: string,
  kundensichtbar: boolean,
  clientUuid: string = crypto.randomUUID(),
): Promise<string> {
  const db = await getDb();
  await db.put("outbox", {
    client_uuid: clientUuid,
    vorgang_id: vorgangId,
    kind: "foto",
    fotoBlob: file,
    fotoName,
    kundensichtbar,
    created_at: new Date().toISOString(),
  });
  notify();
  return clientUuid;
}

export async function queueDokument(
  vorgangId: string,
  file: Blob,
  dokumentName: string,
  kundensichtbar: boolean,
  clientUuid: string = crypto.randomUUID(),
): Promise<string> {
  const db = await getDb();
  await db.put("outbox", {
    client_uuid: clientUuid,
    vorgang_id: vorgangId,
    kind: "dokument",
    dokumentBlob: file,
    dokumentName,
    kundensichtbar,
    created_at: new Date().toISOString(),
  });
  notify();
  return clientUuid;
}

export async function queueStatusChange(vorgangId: string, status: string): Promise<string> {
  const clientUuid = crypto.randomUUID();
  const db = await getDb();
  await db.put("outbox", {
    client_uuid: clientUuid,
    vorgang_id: vorgangId,
    kind: "status",
    statusValue: status,
    created_at: new Date().toISOString(),
  });
  notify();
  return clientUuid;
}

export async function queueVorgang(payload: {
  kunde_id: string;
  anlage_id?: string | null;
  titel: string;
  beschreibung?: string;
  abrechnungsart: string;
  leistungstyp: string;
}): Promise<string> {
  const clientUuid = crypto.randomUUID();
  const db = await getDb();
  await db.put("outbox", {
    client_uuid: clientUuid,
    vorgang_id: null,
    kind: "vorgang",
    vorgangKundeId: payload.kunde_id,
    vorgangAnlageId: payload.anlage_id ?? null,
    vorgangTitel: payload.titel,
    vorgangBeschreibung: payload.beschreibung,
    vorgangAbrechnungsart: payload.abrechnungsart,
    vorgangLeistungstyp: payload.leistungstyp,
    created_at: new Date().toISOString(),
  });
  notify();
  return clientUuid;
}

export async function getOutboxItems(vorgangId?: string): Promise<OutboxItem[]> {
  const db = await getDb();
  const items = await db.getAll("outbox");
  return vorgangId ? items.filter((i) => i.vorgang_id === vorgangId) : items;
}

export async function getOutboxCount(): Promise<number> {
  const db = await getDb();
  return db.count("outbox");
}

let syncing = false;

/** Discards a permanently failed item (the server rejected it outright, a
 * retry would just fail again the same way) so it stops taking up space in
 * the queue and the "nicht synchronisiert" list. */
export async function discardOutboxItem(clientUuid: string): Promise<void> {
  const db = await getDb();
  await db.delete("outbox", clientUuid);
  notify();
}

/** Sends queued items one at a time, oldest first, in original order.
 * A transient failure (network drop, timeout, 5xx) stops the whole run --
 * the same item is retried first on the next sync, preserving order. A
 * permanent rejection (4xx: the server looked at the request and said no)
 * would just fail again identically, so it's marked failed and left for the
 * user to see/discard instead of blocking every later item behind it. */
export async function syncOutbox(): Promise<void> {
  if (syncing || !navigator.onLine) return;
  syncing = true;
  try {
    const db = await getDb();
    const items = (await db.getAll("outbox"))
      .filter((i) => !i.failed)
      .sort((a, b) => (a.created_at < b.created_at ? -1 : 1));

    for (const item of items) {
      try {
        await sendOutboxItem(item);
        await db.delete("outbox", item.client_uuid);
        notify();
      } catch (err) {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
          await db.put("outbox", { ...item, failed: true, errorMessage: err.message });
          notify();
          continue;
        }
        break;
      }
    }
  } finally {
    syncing = false;
  }
}

async function sendOutboxItem(item: OutboxItem): Promise<VorgangEvent | Vorgang> {
  if (item.kind === "vorgang") {
    return apiFetch<Vorgang>("/api/vorgaenge", {
      method: "POST",
      body: JSON.stringify({
        kunde_id: item.vorgangKundeId,
        anlage_id: item.vorgangAnlageId ?? null,
        titel: item.vorgangTitel,
        beschreibung: item.vorgangBeschreibung,
        abrechnungsart: item.vorgangAbrechnungsart,
        leistungstyp: item.vorgangLeistungstyp,
        client_uuid: item.client_uuid,
      }),
    });
  }

  if (item.kind === "status") {
    return apiFetch<Vorgang>(`/api/vorgaenge/${item.vorgang_id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: item.statusValue }),
    });
  }

  if (item.kind === "kommentar") {
    return apiFetch<VorgangEvent>(`/api/vorgaenge/${item.vorgang_id}/events`, {
      method: "POST",
      body: JSON.stringify({
        event_type: "kommentar",
        body: item.body,
        kundensichtbar: item.kundensichtbar,
        client_uuid: item.client_uuid,
      }),
    });
  }

  if (item.kind === "dokument") {
    const formData = new FormData();
    formData.append("file", item.dokumentBlob!, item.dokumentName ?? "dokument");
    formData.append("kundensichtbar", String(item.kundensichtbar ?? false));
    formData.append("client_uuid", item.client_uuid);
    return apiFetchForm<VorgangEvent>(`/api/vorgaenge/${item.vorgang_id}/events/dokument`, formData);
  }

  const formData = new FormData();
  formData.append("file", item.fotoBlob!, item.fotoName ?? "foto.jpg");
  formData.append("kundensichtbar", String(item.kundensichtbar ?? false));
  formData.append("client_uuid", item.client_uuid);
  return apiFetchForm<VorgangEvent>(`/api/vorgaenge/${item.vorgang_id}/events/foto`, formData);
}
