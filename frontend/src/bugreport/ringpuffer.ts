// Fester Speicherbedarf und O(1) push: bei voller Kapazitaet wird der aelteste
// Eintrag ueberschrieben, statt das Array zu verschieben.
export class Ringpuffer<T> {
  private readonly daten: (T | undefined)[];
  private start = 0;
  private anzahl = 0;

  constructor(private readonly kapazitaet: number) {
    if (!Number.isInteger(kapazitaet) || kapazitaet < 1) {
      throw new RangeError("Kapazitaet muss eine positive ganze Zahl sein");
    }
    this.daten = new Array<T | undefined>(kapazitaet);
  }

  push(eintrag: T): void {
    const ende = (this.start + this.anzahl) % this.kapazitaet;
    this.daten[ende] = eintrag;
    if (this.anzahl < this.kapazitaet) {
      this.anzahl += 1;
    } else {
      this.start = (this.start + 1) % this.kapazitaet;
    }
  }

  // Aelteste zuerst.
  toArray(): T[] {
    const ergebnis: T[] = [];
    for (let i = 0; i < this.anzahl; i += 1) {
      ergebnis.push(this.daten[(this.start + i) % this.kapazitaet] as T);
    }
    return ergebnis;
  }

  clear(): void {
    this.daten.fill(undefined);
    this.start = 0;
    this.anzahl = 0;
  }

  get laenge(): number {
    return this.anzahl;
  }
}
