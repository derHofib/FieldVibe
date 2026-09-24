/** Schalter (Abschnitt 4.2). Eigenes <button role="switch">, kein natives
 * <input type="checkbox"> -- so lassen sich Knopf-Position und Farbe frei
 * animieren, ohne die native Checkbox zu verstecken/nachzubauen. */
export function Switch({
  checked,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (wert: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className="relative inline-flex h-[31px] w-[51px] shrink-0 items-center rounded-[16px] p-0.5 transition-colors duration-200"
      style={{ backgroundColor: checked ? "var(--switch-on)" : "var(--fill2)" }}
    >
      <span
        className="h-[27px] w-[27px] rounded-full bg-white shadow-[0_2px_5px_rgba(0,0,0,.2)] transition-transform duration-200"
        style={{ transform: checked ? "translateX(20px)" : "translateX(0)" }}
      />
    </button>
  );
}
