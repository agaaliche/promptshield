/** Excel-like grid for blacklist term entry with copy/paste support. */

import { useState, useCallback, useRef, useEffect } from "react";

const DEFAULT_COLS = 3;
const DEFAULT_VISIBLE_ROWS = 10;
const MAX_COLS = 10;
const MAX_ROWS = 100;
const CELL_HEIGHT = 28;
const CELL_MIN_WIDTH = 100;

export type BlacklistAction = "none" | "tokenize" | "remove";

export interface BlacklistGridProps {
  /** Current grid data (cols × rows). */
  cells: string[][];
  /** Called whenever any cell changes. */
  onCellsChange: (cells: string[][]) => void;
  /** Current action mode. */
  action: BlacklistAction;
  /** Called when action changes. */
  onActionChange: (action: BlacklistAction) => void;
  /** Map of cell key "row,col" → match status. */
  matchStatus?: Map<string, "matched" | "no-match" | "exists">;
}

/** Create an empty grid with given dimensions. */
export function createEmptyGrid(rows = DEFAULT_VISIBLE_ROWS, cols = DEFAULT_COLS): string[][] {
  return Array.from({ length: rows }, () => Array(cols).fill(""));
}

export default function BlacklistGrid({
  cells,
  onCellsChange,
  action,
  onActionChange,
  matchStatus,
}: BlacklistGridProps) {
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null);
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const numCols = cells[0]?.length ?? DEFAULT_COLS;
  const numRows = cells.length;

  // Focus input when editing starts
  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingCell]);

  const updateCell = useCallback((row: number, col: number, value: string) => {
    const next = cells.map(r => [...r]);
    // Grow grid if needed
    while (next.length <= row) next.push(Array(numCols).fill(""));
    while (next[row].length <= col) next[row].push("");
    next[row][col] = value;
    onCellsChange(next);
  }, [cells, numCols, onCellsChange]);

  // Handle paste — supports multi-cell paste from Excel/CSV
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault();
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;

    const startRow = selectedCell?.row ?? 0;
    const startCol = selectedCell?.col ?? 0;

    // Parse pasted text: tab-separated columns, newline-separated rows
    const pastedRows = text.split(/\r?\n/).filter(line => line.length > 0);
    const next = cells.map(r => [...r]);

    for (let ri = 0; ri < pastedRows.length && startRow + ri < MAX_ROWS; ri++) {
      const cols = pastedRows[ri].split(/\t|,(?=(?:[^"]*"[^"]*")*[^"]*$)/);
      const targetRow = startRow + ri;
      while (next.length <= targetRow) next.push(Array(numCols).fill(""));
      for (let ci = 0; ci < cols.length && startCol + ci < MAX_COLS; ci++) {
        const targetCol = startCol + ci;
        while (next[targetRow].length <= targetCol) next[targetRow].push("");
        // Strip surrounding quotes from CSV
        next[targetRow][targetCol] = cols[ci].replace(/^"|"$/g, "").trim();
      }
    }
    onCellsChange(next);
    setEditingCell(null);
  }, [cells, selectedCell, numCols, onCellsChange]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!selectedCell) return;
    const { row, col } = selectedCell;

    if (e.key === "Enter") {
      if (editingCell) {
        setEditingCell(null);
        // Move down
        if (row + 1 < numRows) setSelectedCell({ row: row + 1, col });
      } else {
        setEditingCell({ row, col });
      }
      e.preventDefault();
    } else if (e.key === "Tab") {
      e.preventDefault();
      setEditingCell(null);
      if (e.shiftKey) {
        if (col > 0) setSelectedCell({ row, col: col - 1 });
        else if (row > 0) setSelectedCell({ row: row - 1, col: numCols - 1 });
      } else {
        if (col < numCols - 1) setSelectedCell({ row, col: col + 1 });
        else if (row < numRows - 1) setSelectedCell({ row: row + 1, col: 0 });
      }
    } else if (e.key === "Escape") {
      setEditingCell(null);
    } else if (!editingCell) {
      if (e.key === "ArrowUp" && row > 0) setSelectedCell({ row: row - 1, col });
      if (e.key === "ArrowDown" && row < numRows - 1) setSelectedCell({ row: row + 1, col });
      if (e.key === "ArrowLeft" && col > 0) setSelectedCell({ row, col: col - 1 });
      if (e.key === "ArrowRight" && col < numCols - 1) setSelectedCell({ row, col: col + 1 });
      if (e.key === "Delete" || e.key === "Backspace") {
        updateCell(row, col, "");
      }
      // Start editing on any printable character
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
        setEditingCell({ row, col });
        updateCell(row, col, "");
      }
    }
  }, [selectedCell, editingCell, numRows, numCols, updateCell]);

  const filledCellCount = cells.flat().filter(c => c.trim().length > 0).length;

  // Column width based on available space
  const colWidth = Math.max(CELL_MIN_WIDTH, Math.floor(280 / numCols));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Grid */}
      <div
        ref={gridRef}
        style={{
          border: "1px solid var(--border-color)",
          borderRadius: 4,
          overflow: "auto",
          maxHeight: DEFAULT_VISIBLE_ROWS * CELL_HEIGHT + 2,
          background: "rgba(0,0,0,0.15)",
        }}
        onPaste={handlePaste}
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        {/* Column headers */}
        <div style={{ display: "flex", position: "sticky", top: 0, zIndex: 1 }}>
          <div style={{
            width: 32, minWidth: 32, height: 24,
            background: "var(--bg-tertiary, rgba(0,0,0,0.3))",
            borderBottom: "1px solid var(--border-color)",
            borderRight: "1px solid var(--border-color)",
          }} />
          {Array.from({ length: numCols }, (_, ci) => (
            <div key={ci} style={{
              width: colWidth, minWidth: colWidth, height: 24,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: 600,
              color: "var(--text-muted)",
              background: "var(--bg-tertiary, rgba(0,0,0,0.3))",
              borderBottom: "1px solid var(--border-color)",
              borderRight: ci < numCols - 1 ? "1px solid var(--border-color)" : "none",
            }}>
              {String.fromCharCode(65 + ci)}
            </div>
          ))}
        </div>

        {/* Data rows */}
        {cells.map((row, ri) => (
          <div key={ri} style={{ display: "flex" }}>
            {/* Row number */}
            <div style={{
              width: 32, minWidth: 32, height: CELL_HEIGHT,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "var(--text-muted)",
              background: "rgba(0,0,0,0.1)",
              borderBottom: "1px solid rgba(255,255,255,0.04)",
              borderRight: "1px solid var(--border-color)",
              flexShrink: 0,
            }}>
              {ri + 1}
            </div>
            {row.map((cellVal, ci) => {
              const isSelected = selectedCell?.row === ri && selectedCell?.col === ci;
              const isEditing = editingCell?.row === ri && editingCell?.col === ci;
              const key = `${ri},${ci}`;
              const status = matchStatus?.get(key);
              let cellBg = "transparent";
              if (status === "matched") cellBg = "rgba(76,175,80,0.15)";
              else if (status === "no-match") cellBg = "rgba(255,152,0,0.15)";
              else if (status === "exists") cellBg = "rgba(33,150,243,0.12)";

              return (
                <div
                  key={ci}
                  onClick={() => {
                    setSelectedCell({ row: ri, col: ci });
                    if (!isEditing) setEditingCell(null);
                  }}
                  onDoubleClick={() => setEditingCell({ row: ri, col: ci })}
                  style={{
                    width: colWidth, minWidth: colWidth, height: CELL_HEIGHT,
                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                    borderRight: ci < numCols - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                    outline: isSelected ? "2px solid var(--accent-primary)" : "none",
                    outlineOffset: -2,
                    background: cellBg,
                    padding: 0,
                    cursor: "cell",
                    position: "relative",
                  }}
                >
                  {isEditing ? (
                    <input
                      ref={inputRef}
                      value={cellVal}
                      onChange={(e) => updateCell(ri, ci, e.target.value)}
                      onBlur={() => setEditingCell(null)}
                      style={{
                        width: "100%", height: "100%",
                        border: "none", outline: "none",
                        background: "rgba(0,0,0,0.3)",
                        color: "var(--text-primary)",
                        fontSize: 12, padding: "0 6px",
                        fontFamily: "inherit",
                      }}
                    />
                  ) : (
                    <div style={{
                      width: "100%", height: "100%",
                      display: "flex", alignItems: "center",
                      padding: "0 6px",
                      fontSize: 12,
                      color: cellVal ? "var(--text-primary)" : "var(--text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}>
                      {cellVal || ""}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Status + action bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 8, flexWrap: "wrap",
      }}>
        {/* Action toggles */}
        <div style={{ display: "flex", gap: 4 }}>
          <button
            className={`btn-sm ${action === "tokenize" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => onActionChange(action === "tokenize" ? "none" : "tokenize")}
            style={{ fontSize: 11, padding: "4px 10px" }}
            title="Flag matched regions for tokenization"
          >
            Tokenize
          </button>
          <button
            className={`btn-sm ${action === "remove" ? "btn-danger" : "btn-ghost"}`}
            onClick={() => onActionChange(action === "remove" ? "none" : "remove")}
            style={{ fontSize: 11, padding: "4px 10px" }}
            title="Flag matched regions for removal"
          >
            Remove
          </button>
        </div>

        {/* Term count */}
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
          {filledCellCount} term{filledCellCount !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}
