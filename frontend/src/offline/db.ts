import { openDB, type DBSchema, type IDBPDatabase } from "idb";

import type { Anlage, FeedCard, Kunde, VorgangEvent } from "../types";

export interface OutboxItem {
  client_uuid: string;
  // "vorgang" hat noch keinen Server-Vorgang und damit keine vorgang_id --
  // die entsteht erst beim erfolgreichen Sync (siehe app/api/routes/
  // vorgaenge.py::create_vorgang, das denselben client_uuid als
  // Idempotenz-Schluessel nutzt wie VorgangEvent.client_uuid).
  vorgang_id: string | null;
  kind: "kommentar" | "foto" | "vorgang";
  created_at: string;
  // "kommentar": JSON-Body fuer POST .../events
  body?: string;
  kundensichtbar?: boolean;
  // "foto": Blob wird lokal gehalten, bis online gesendet werden kann
  fotoBlob?: Blob;
  fotoName?: string;
  // "vorgang": Felder fuer die komplette Neuanlage eines Vorgangs offline
  vorgangKundeId?: string;
  vorgangAnlageId?: string | null;
  vorgangTitel?: string;
  vorgangBeschreibung?: string;
  vorgangAbrechnungsart?: string;
  vorgangLeistungstyp?: string;
}

interface SocialCrmDB extends DBSchema {
  feed: { key: string; value: FeedCard };
  vorgang_events: { key: number; value: VorgangEvent; indexes: { "by-vorgang": string } };
  kunden: { key: string; value: Kunde };
  anlagen: { key: string; value: Anlage };
  outbox: { key: string; value: OutboxItem };
}

let dbPromise: Promise<IDBPDatabase<SocialCrmDB>> | null = null;

export function getDb(): Promise<IDBPDatabase<SocialCrmDB>> {
  if (!dbPromise) {
    dbPromise = openDB<SocialCrmDB>("socialcrm-offline", 1, {
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
