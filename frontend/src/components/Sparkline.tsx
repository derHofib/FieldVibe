// Winziger Verlaufs-Graph fuer Prozentwerte (0-100), ohne Chart-Library --
// fuer eine Handvoll Punkte in der Server-Auslastung reicht ein simples
// SVG-Polyline auf fixer 0-100-Skala.
export function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) {
    return <svg className="h-7 w-20 shrink-0" />;
  }
  const width = 100;
  const height = 28;
  const padding = 2;
  const points = values
    .map((value, i) => {
      const x = padding + (i / (values.length - 1)) * (width - padding * 2);
      const y = padding + (1 - value / 100) * (height - padding * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-7 w-20 shrink-0">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
