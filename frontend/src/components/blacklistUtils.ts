/** Shared constants and utilities for the BlacklistGrid. */

export const MAX_COLS = 10;
export const MAX_ROWS = 100;

/** Create an empty grid with given dimensions. */
export function createEmptyGrid(rows = MAX_ROWS, cols = MAX_COLS): string[][] {
  return Array.from({ length: rows }, () => Array(cols).fill(""));
}
