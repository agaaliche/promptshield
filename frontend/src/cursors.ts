/**
 * Custom CSS cursor values with high-contrast outlines (dark stroke + white outline)
 * so cursors remain visible on both light and dark backgrounds.
 */

/** Encode raw SVG markup into a CSS `cursor: url(…) hotX hotY, fallback` value. */
function svgCursor(rawSvg: string, hotX: number, hotY: number, fallback: string): string {
  const encoded = rawSvg
    .replace(/</g, "%3C")
    .replace(/>/g, "%3E")
    .replace(/#/g, "%23");
  return `url("data:image/svg+xml,${encoded}") ${hotX} ${hotY}, ${fallback}`;
}

// ── Crosshair (32×32, hotspot at center) ──
// Dark cross-lines with white outline, gap in centre for precision.
const CROSSHAIR_SVG =
  `<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'>` +
  // White outline layer (thicker, drawn first)
  `<line x1='16' y1='0' x2='16' y2='12' stroke='white' stroke-width='3'/>` +
  `<line x1='16' y1='20' x2='16' y2='32' stroke='white' stroke-width='3'/>` +
  `<line x1='0' y1='16' x2='12' y2='16' stroke='white' stroke-width='3'/>` +
  `<line x1='20' y1='16' x2='32' y2='16' stroke='white' stroke-width='3'/>` +
  // Dark centre layer (thinner, drawn on top)
  `<line x1='16' y1='0' x2='16' y2='12' stroke='#222' stroke-width='1.5'/>` +
  `<line x1='16' y1='20' x2='16' y2='32' stroke='#222' stroke-width='1.5'/>` +
  `<line x1='0' y1='16' x2='12' y2='16' stroke='#222' stroke-width='1.5'/>` +
  `<line x1='20' y1='16' x2='32' y2='16' stroke='#222' stroke-width='1.5'/>` +
  `</svg>`;

export const CURSOR_CROSSHAIR = svgCursor(CROSSHAIR_SVG, 16, 16, "crosshair");

// ── Grab — circle-dot (16×16, hotspot centre) ──
// Open circle with dot: signals "draggable", visible on any background.
const GRAB_SVG =
  `<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'>` +
  `<circle cx='8' cy='8' r='6' fill='none' stroke='white' stroke-width='3'/>` +
  `<circle cx='8' cy='8' r='6' fill='none' stroke='#222' stroke-width='1.5'/>` +
  `<circle cx='8' cy='8' r='2' fill='white'/>` +
  `<circle cx='8' cy='8' r='1.2' fill='#222'/>` +
  `</svg>`;

export const CURSOR_GRAB = svgCursor(GRAB_SVG, 8, 8, "grab");

// ── Grabbing — filled circle (16×16, hotspot centre) ──
// Solid dot: signals "actively dragging".
const GRABBING_SVG =
  `<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'>` +
  `<circle cx='8' cy='8' r='6' fill='none' stroke='white' stroke-width='3'/>` +
  `<circle cx='8' cy='8' r='6' fill='none' stroke='#222' stroke-width='1.5'/>` +
  `<circle cx='8' cy='8' r='3.5' fill='white'/>` +
  `<circle cx='8' cy='8' r='2.5' fill='#222'/>` +
  `</svg>`;

export const CURSOR_GRABBING = svgCursor(GRABBING_SVG, 8, 8, "grabbing");
