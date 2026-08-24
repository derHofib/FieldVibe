import { openDB, type DBSchema, type IDBPDatabase } from "idb";

import type { Anlage, FeedCard, Kunde, VorgangEvent } from "../types";

export interface OutboxItem {
  client_uuid: string;
  // "vorgang" hat noch keinen Server-Vorgang und damit keine vorgang_id --
  // die entsteht erst beim erfolgreichen Sync (siehe app/api/routes/
  // vorgaenge.py::create_vorgang, das denselben client_uuid als
  // Idempotenz-Schluessel nutzt wie VorgangEvent.client_uuid).
  vorgang_id: string | null;
  kind: "kommentar" | "foto" | "dokument" | "vorgang" | "status";
  created_at: string;
  // "kommentar": JSON-Body fuer POST .../events
  body?: string;
  kundensichtbar?: boolean;
  // "foto": Blob wird lokal gehalten, bis online gesendet werden kann
  fotoBlob?: Blob;
  fotoName?: string;
  // "dokument": analog zu "foto", aber beliebiger Dateityp
  dokumentBlob?: Blob;
  dokumentName?: string;
  // "vorgang": Felder fuer die komplette Neuanlage eines Vorgangs offline
  vorgangKundeId?: string;
  vorgangAnlageId?: string | null;
  vorgangTitel?: string;
  vorgangBeschreibung?: string;
  vorgangAbrechnungsart?: string;
  vorgangLeistungstyp?: string;
  // "status": neuer Status fuer einen bestehenden Vorgang
  statusValue?: string;
  // Vom Server abgelehnt (z. B. 409 "bereits abgeschlossen") statt eines
  // Netzwerkfehlers -- ein erneuter Versuch wuerde denselben Fehler
  // liefern, darf aber nicht den Rest der Warteschlange blockieren.
  failed?: boolean;
  errorMessage?: string;
}

interface FieldVibeDB extends DBSchema {
  feed: { key: string; value: FeedCard };
  vorgang_events: { key: number; value: VorgangEvent; indexes: { "by-vorgang": string } };
  kunden: { key: string; value: Kunde };
  anlagen: { key: string; value: Anlage };
  outbox: { key: string; value: OutboxItem };
}

let dbPromise: Promise<IDBPDatabase<FieldVibeDB>> | null = null;

export function getDb(): Promise<IDBPDatabase<FieldVibeDB>> {
  if (!dbPromise) {
    dbPromise = openDB<FieldVibeDB>("fieldvibe-offline", 1, {
      upgrade(db) {
        db.createObjectStore("feed", { keyPath: "id" });
        const events = db.createObjectStore("vorgang_events", { keyPath: "id" });
        events.createIndex("by-vorgang", "vorgang_id");
        db.createObjectStore("kunden", { keyPath: "id" });
        db.createObjectStore("anlagen", { keyPath: "id" });
        db.createObjectStore("outbox", { keyPath: "client_uuid" });
      },
    });
  }
  return dbPromise;
}

/** Wischt alle lokal zwischengespeicherten Daten (Cache + Outbox) --
 * bei einem geteilten Geraet (Firmenhandy/-tablet) duerfen weder
 * Kunden-/Vorgangsdaten des vorherigen Nutzers sichtbar bleiben, noch
 * dessen noch nicht synchronisierte Outbox-Eintraege spaeter unter der
 * Identitaet des naechsten angemeldeten Nutzers hochgeladen werden. */
export async function clearAllOfflineData(): Promise<void> {
  const db = await getDb();
  await Promise.all(
    (["feed", "vorgang_events", "kunden", "anlagen", "outbox"] as const).map((store) =>
      db.clear(store),
    ),
  );
}
