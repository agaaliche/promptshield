/**
 * Centralized z-index scale (M15).
 *
 * All z-index values in the app should reference these constants
 * to prevent layering conflicts.  Grouped by stacking context:
 *
 *   Content layer    (1-10)   — page elements, region boxes
 *   Controls layer   (20-50)  — toolbars, sidebars, floating panels
 *   Overlay layer    (100)    — modal backdrop, dialogs
 *   Top-level layer  (10000)  — file dialogs, export dialog
 *   Toast layer      (99999)  — snackbar / notifications
 */

// ── Content layer ────────────────────────────────────────────────
/** Base region box on the document page */
export const Z_REGION = 2;
/** Hovered region */
export const Z_REGION_HOVER = 4;
/** Selected region / edit panel anchor */
export const Z_REGION_SELECTED = 5;
/** Region resize handles */
export const Z_REGION_HANDLE = 6;
/** Page scroll-indicators */
export const Z_PAGE_INDICATOR = 8;
/** Drawing canvas / lasso overlay */
export const Z_DRAW_CANVAS = 9;
/** Region edit panel (inline) */
export const Z_REGION_EDIT_PANEL = 10;
/** Region type-picker popup */
export const Z_REGION_TYPE_PICKER = 15;

// ── Controls layer ───────────────────────────────────────────────
/** Page navigator bar */
export const Z_PAGE_NAV = 20;
/** Cursor-tool & multi-select floating toolbars */
export const Z_TOOLBAR = 30;
/** PII type picker (sidebar-level) */
export const Z_SIDEBAR_PICKER = 40;
/** Bottom bar / status bar */
export const Z_BOTTOM_BAR = 41;
/** Sidebar floating panels (resize, dropdown) */
export const Z_SIDEBAR_PANEL = 50;

// ── Overlay layer ────────────────────────────────────────────────
/** Modal backdrop / dialog overlays */
export const Z_MODAL = 100;
/** Inline fullscreen popover (multi-select bulk-edit) */
export const Z_POPOVER = 1000;

// ── Top-level layer ──────────────────────────────────────────────
/** Autodetect panel, file dialogs, export dialog */
export const Z_TOP_DIALOG = 10000;

// ── Toast layer ──────────────────────────────────────────────────
/** Snackbar / toast notifications — always on top */
export const Z_TOAST = 99999;
