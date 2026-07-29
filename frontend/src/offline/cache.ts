import { getDb } from "./db";
import type { Anlage, FeedCard, Kunde, VorgangEvent } from "../types";

// Write-through cache for offline reads. Deliberately scoped to what a
// Techniker actually opened (feed page(s) seen, Vorgaenge/Kunden/Anlagen
// visited) rather than a blanket "everything for the next 7 Tage" --
// that filter is defined against Termine (Abschnitt 6), which don't exist
// until Phase 5. Once they do, a background prefetch keyed off upcoming
// Termine can populate the same stores ahead of time.

export async function cacheFeedItems(items: FeedCard[]): Promise<void> {
  const db = await getDb();
  const tx = db.transaction("feed", "readwrite");
  await Promise.all(items.map((item) => tx.store.put(item)));
  await tx.done;
}

export async function getCachedFeedItems(): Promise<FeedCard[]> {
  const db = await getDb();
  const items = await db.getAll("feed");
  return items.sort((a, b) => (a.last_activity_at < b.last_activity_at ? 1 : -1));
}

export async function cacheEvents(events: VorgangEvent[]): Promise<void> {
  const db = await getDb();
  const tx = db.transaction("vorgang_events", "readwrite");
  await Promise.all(events.map((event) => tx.store.put(event)));
  await tx.done;
}

export async function getCachedEvents(vorgangId: string): Promise<VorgangEvent[]> {
  const db = await getDb();
  return db.getAllFromIndex("vorgang_events", "by-vorgang", vorgangId);
}

export async function cacheKunde(kunde: Kunde): Promise<void> {
  const db = await getDb();
  await db.put("kunden", kunde);
}

export async function getCachedKunde(id: string): Promise<Kunde | undefined> {
  const db = await getDb();
  return db.get("kunden", id);
}

export async function cacheAnlage(anlage: Anlage): Promise<void> {
  const db = await getDb();
  await db.put("anlagen", anlage);
}

export async function getCachedAnlage(id: string): Promise<Anlage | undefined> {
  const db = await getDb();
  return db.get("anlagen", id);
}
