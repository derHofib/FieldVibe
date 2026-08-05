export function formatMinutenAlsHHMM(gesamtMinuten: number): string {
  const minutenGerundet = Math.round(gesamtMinuten);
  const stunden = Math.floor(minutenGerundet / 60);
  const minuten = minutenGerundet % 60;
  return `${stunden}:${String(minuten).padStart(2, "0")}`;
}

export function formatStundenAlsHHMM(stunden: number): string {
  return formatMinutenAlsHHMM(stunden * 60);
}

export function formatSekundenAlsHHMM(sekunden: number): string {
  return formatMinutenAlsHHMM(sekunden / 60);
}
