const CSS_ID = 'recoverai-liquid-glass-injected';

export function injectLiquidGlassCSS() {
  if (typeof window === 'undefined') return;
  if (document.getElementById(CSS_ID)) return;

  const css = `
/* ========================================================================
   LIQUID GLASS — Normal CSS (NOT @utility) so Tailwind 4 doesn't strip it.
   ======================================================================== */
.liquid-glass {
  position: relative;
  background: rgba(13, 15, 22, 0.42);
  backdrop-filter: saturate(160%) blur(20px);
  -webkit-backdrop-filter: saturate(160%) blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow:
    0 16px 48px -16px rgba(0, 0, 0, 0.55),
    0 4px 12px -4px rgba(0, 0, 0, 0.4),
    inset 0 0 0 1px rgba(255, 255, 255, 0.02);
  transition:
    background 0.25s ease,
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}
.liquid-glass::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(
    160deg,
    rgba(255, 255, 255, 0.22) 0%,
    rgba(255, 255, 255, 0.04) 28%,
    rgba(255, 255, 255, 0) 52%,
    rgba(255, 255, 255, 0.08) 78%,
    rgba(255, 255, 255, 0.18) 100%
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0.85;
  transition: opacity 0.25s ease;
}
.liquid-glass::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0) 32%,
    rgba(255, 255, 255, 0) 100%
  );
  pointer-events: none;
  mix-blend-mode: screen;
  opacity: 0.9;
  transition: opacity 0.25s ease;
}
.liquid-glass:hover {
  background: rgba(20, 24, 34, 0.5);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow:
    0 20px 56px -16px rgba(0, 0, 0, 0.6),
    0 6px 16px -4px rgba(0, 0, 0, 0.45),
    inset 0 0 0 1px rgba(255, 255, 255, 0.04);
}
.liquid-glass:hover::before { opacity: 1; }
.liquid-glass:hover::after  { opacity: 1;
}`;
  const style = document.createElement('style');
  style.id = CSS_ID;
  style.textContent = css;
  document.head.appendChild(style);
}