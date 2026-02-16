/** Excel-like grid for blacklist term entry with copy/paste support. */

import { useState, useCallback, useRef, useEffect } from "react";
import { Key, Trash2 } from "lucide-react";

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
export function createEmptyGrid(rows = MAX_ROWS, cols = MAX_COLS): string[][] {
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
  const [selectionEnd, setSelectionEnd] = useState<{ row: number; col: number } | null>(null);
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [copiedBounds, setCopiedBounds] = useState<{ minRow: number; maxRow: number; minCol: number; maxCol: number } | null>(null);
  
  // Undo/redo stacks for grid-local history
  const [undoStack, setUndoStack] = useState<string[][][]>([]);
  const [redoStack, setRedoStack] = useState<string[][][]>([]);
  
  const gridRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const numCols = cells[0]?.length ?? DEFAULT_COLS;
  const numRows = cells.length;

  // Compute selection range bounds
  const getSelectionBounds = useCallback(() => {
    if (!selectedCell) return null;
    const end = selectionEnd ?? selectedCell;
    return {
      minRow: Math.min(selectedCell.row, end.row),
      maxRow: Math.max(selectedCell.row, end.row),
      minCol: Math.min(selectedCell.col, end.col),
      maxCol: Math.max(selectedCell.col, end.col),
    };
  }, [selectedCell, selectionEnd]);

  const isInSelection = useCallback((row: number, col: number) => {
    const bounds = getSelectionBounds();
    if (!bounds) return false;
    return row >= bounds.minRow && row <= bounds.maxRow && col >= bounds.minCol && col <= bounds.maxCol;
  }, [getSelectionBounds]);

  const isInCopiedBounds = useCallback((row: number, col: number) => {
    if (!copiedBounds) return false;
    return row >= copiedBounds.minRow && row <= copiedBounds.maxRow && col >= copiedBounds.minCol && col <= copiedBounds.maxCol;
  }, [copiedBounds]);

  // Focus input when editing starts
  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingCell]);

  // Push current state to undo stack before making changes
  const pushUndo = useCallback(() => {
    setUndoStack(prev => [...prev.slice(-49), cells.map(r => [...r])]);
    setRedoStack([]);
  }, [cells]);

  // Undo: restore last state from undo stack
  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    setUndoStack(s => s.slice(0, -1));
    setRedoStack(s => [...s, cells.map(r => [...r])]);
    onCellsChange(prev);
  }, [undoStack, cells, onCellsChange]);

  // Redo: restore last state from redo stack
  const handleRedo = useCallback(() => {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setRedoStack(s => s.slice(0, -1));
    setUndoStack(s => [...s, cells.map(r => [...r])]);
    onCellsChange(next);
  }, [redoStack, cells, onCellsChange]);

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
    e.stopPropagation();
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;

    pushUndo();
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
    setSelectionEnd(null);
    setCopiedBounds(null);
  }, [cells, selectedCell, numCols, onCellsChange, pushUndo]);

  // Handle copy — copies selected range as tab-separated text
  const handleCopy = useCallback((e: React.ClipboardEvent) => {
    if (editingCell) return; // Let the input handle copy
    const bounds = getSelectionBounds();
    if (!bounds) return;
    e.preventDefault();
    e.stopPropagation();

    const lines: string[] = [];
    for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
      const rowCells: string[] = [];
      for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
        rowCells.push(cells[r]?.[c] ?? "");
      }
      lines.push(rowCells.join("\t"));
    }
    e.clipboardData.setData("text/plain", lines.join("\n"));
    setCopiedBounds(bounds);
  }, [cells, editingCell, getSelectionBounds]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Stop propagation for clipboard/select/undo shortcuts to prevent global shortcuts
    if ((e.ctrlKey || e.metaKey) && ["c", "v", "a", "z", "y"].includes(e.key.toLowerCase())) {
      e.stopPropagation();
      e.preventDefault();
      // Ctrl+A: select all cells in the grid
      if (e.key.toLowerCase() === "a") {
        setSelectedCell({ row: 0, col: 0 });
        setSelectionEnd({ row: numRows - 1, col: numCols - 1 });
        setEditingCell(null);
        setCopiedBounds(null);
      }
      // Ctrl+Z: undo
      if (e.key.toLowerCase() === "z") {
        handleUndo();
      }
      // Ctrl+Y: redo
      if (e.key.toLowerCase() === "y") {
        handleRedo();
      }
      // Ctrl+C and Ctrl+V are handled by onCopy/onPaste events
      return;
    }

    if (!selectedCell) return;
    const { row, col } = selectedCell;
    const anchor = selectionEnd ?? selectedCell;

    if (e.key === "Enter") {
      if (editingCell) {
        setEditingCell(null);
        setSelectionEnd(null);
        // Move down
        if (row + 1 < numRows) setSelectedCell({ row: row + 1, col });
      } else {
        setEditingCell({ row, col });
      }
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === "Tab") {
      e.preventDefault();
      e.stopPropagation();
      setEditingCell(null);
      setSelectionEnd(null);
      if (e.shiftKey) {
        if (col > 0) setSelectedCell({ row, col: col - 1 });
        else if (row > 0) setSelectedCell({ row: row - 1, col: numCols - 1 });
      } else {
        if (col < numCols - 1) setSelectedCell({ row, col: col + 1 });
        else if (row < numRows - 1) setSelectedCell({ row: row + 1, col: 0 });
      }
    } else if (e.key === "Escape") {
      setEditingCell(null);
      setSelectionEnd(null);
      setCopiedBounds(null);
      e.stopPropagation();
    } else if (!editingCell) {
      // Arrow keys with/without Shift for range selection
      if (e.key === "ArrowUp") {
        const newRow = Math.max(0, (e.shiftKey ? anchor.row : row) - 1);
        if (e.shiftKey) setSelectionEnd({ row: newRow, col: anchor.col });
        else { setSelectedCell({ row: newRow, col }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowDown") {
        const newRow = Math.min(numRows - 1, (e.shiftKey ? anchor.row : row) + 1);
        if (e.shiftKey) setSelectionEnd({ row: newRow, col: anchor.col });
        else { setSelectedCell({ row: newRow, col }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowLeft") {
        const newCol = Math.max(0, (e.shiftKey ? anchor.col : col) - 1);
        if (e.shiftKey) setSelectionEnd({ row: anchor.row, col: newCol });
        else { setSelectedCell({ row, col: newCol }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowRight") {
        const newCol = Math.min(numCols - 1, (e.shiftKey ? anchor.col : col) + 1);
        if (e.shiftKey) setSelectionEnd({ row: anchor.row, col: newCol });
        else { setSelectedCell({ row, col: newCol }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        // Clear all cells in selection
        const bounds = getSelectionBounds();
        if (bounds) {
          pushUndo();
          const next = cells.map(r => [...r]);
          for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
            for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
              if (next[r]) next[r][c] = "";
            }
          }
          onCellsChange(next);
        }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
        // Start editing on any printable character
        pushUndo();
        setEditingCell({ row, col });
        setSelectionEnd(null);
        updateCell(row, col, "");
        e.stopPropagation();
      }
    }
  }, [selectedCell, selectionEnd, editingCell, numRows, numCols, updateCell, getSelectionBounds, cells, onCellsChange, handleUndo, handleRedo, pushUndo]);

  // Select entire column
  const selectColumn = useCallback((col: number) => {
    setSelectedCell({ row: 0, col });
    setSelectionEnd({ row: numRows - 1, col });
    setEditingCell(null);
    setCopiedBounds(null);
  }, [numRows]);

  // Select entire row
  const selectRow = useCallback((row: number) => {
    setSelectedCell({ row, col: 0 });
    setSelectionEnd({ row, col: numCols - 1 });
    setEditingCell(null);
    setCopiedBounds(null);
  }, [numCols]);

  // Mouse drag handlers for range selection
  const handleCellMouseDown = useCallback((row: number, col: number, e: React.MouseEvent) => {
    if (e.shiftKey && selectedCell) {
      setSelectionEnd({ row, col });
    } else {
      setSelectedCell({ row, col });
      setSelectionEnd(null);
      setIsDragging(true);
    }
    setEditingCell(null);
    setCopiedBounds(null);
  }, [selectedCell]);

  const handleCellMouseEnter = useCallback((row: number, col: number) => {
    if (isDragging) {
      setSelectionEnd({ row, col });
    }
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Global mouseup listener for drag end
  useEffect(() => {
    const handleGlobalMouseUp = () => setIsDragging(false);
    window.addEventListener("mouseup", handleGlobalMouseUp);
    return () => window.removeEventListener("mouseup", handleGlobalMouseUp);
  }, []);

  const filledCellCount = cells.flat().filter(c => c.trim().length > 0).length;

  // Column width based on available space
  const colWidth = Math.max(CELL_MIN_WIDTH, Math.floor(280 / numCols));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, minHeight: 0 }}>
      {/* Grid */}
      <div
        ref={gridRef}
        data-blacklist-grid
        style={{
          border: "1px solid var(--border-color)",
          borderRadius: 4,
          overflow: "auto",
          flex: 1,
          minHeight: 0,
          background: "rgba(0,0,0,0.15)",
        }}
        onPaste={handlePaste}
        onCopy={handleCopy}
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        {/* Column headers */}
        <div style={{ display: "flex", position: "sticky", top: 0, zIndex: 1 }}>
          <div style={{
            width: 32, minWidth: 32, height: 24,
            background: "#d6e6f5",
            borderBottom: "1px solid #a8c5e0",
            borderRight: "1px solid #a8c5e0",
          }} />
          {Array.from({ length: numCols }, (_, ci) => (
            <div
              key={ci}
              onClick={() => selectColumn(ci)}
              style={{
                width: colWidth, minWidth: colWidth, height: 24,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, fontWeight: 600,
                color: "#1a4971",
                background: "#d6e6f5",
                borderBottom: "1px solid #a8c5e0",
                borderRight: ci < numCols - 1 ? "1px solid #a8c5e0" : "none",
                cursor: "pointer",
              }}
            >
              {String.fromCharCode(65 + ci)}
            </div>
          ))}
        </div>

        {/* Data rows */}
        {cells.map((row, ri) => (
          <div key={ri} style={{ display: "flex" }}>
            {/* Row number */}
            <div
              onClick={() => selectRow(ri)}
              style={{
                width: 32, minWidth: 32, height: CELL_HEIGHT,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, fontWeight: 600,
                color: "#1a4971",
                background: "#d6e6f5",
                borderBottom: "1px solid #a8c5e0",
                borderRight: "1px solid #a8c5e0",
                flexShrink: 0,
                cursor: "pointer",
              }}
            >
              {ri + 1}
            </div>
            {row.map((cellVal, ci) => {
              const isAnchor = selectedCell?.row === ri && selectedCell?.col === ci;
              const inSelection = isInSelection(ri, ci);
              const inCopied = isInCopiedBounds(ri, ci);
              const isEditing = editingCell?.row === ri && editingCell?.col === ci;
              const key = `${ri},${ci}`;
              const status = matchStatus?.get(key);
              let cellBg = "#ffffff";
              let cellColor = cellVal ? "#111" : "#999";
              if (status === "matched") { cellBg = "#e8f5e9"; cellColor = "#2e7d32"; }
              else if (status === "no-match") { cellBg = "#fff3e0"; cellColor = "#e65100"; }
              else if (status === "exists") { cellBg = "#e3f2fd"; cellColor = "#1565c0"; }
              // Override bg for selection (overrides match status)
              if (inSelection) { cellBg = "#cce5ff"; cellColor = "#111"; }

              // Determine borders - show dashed marching ants border for copied range
              const isLeftEdge = inCopied && ci === copiedBounds?.minCol;
              const isTopEdge = inCopied && ri === copiedBounds?.minRow;
              const isRightEdge = inCopied && ci === copiedBounds?.maxCol;
              const isBottomEdge = inCopied && ri === copiedBounds?.maxRow;

              return (
                <div
                  key={ci}
                  onMouseDown={(e) => handleCellMouseDown(ri, ci, e)}
                  onMouseEnter={() => handleCellMouseEnter(ri, ci)}
                  onMouseUp={handleMouseUp}
                  onDoubleClick={() => setEditingCell({ row: ri, col: ci })}
                  style={{
                    width: colWidth, minWidth: colWidth, height: CELL_HEIGHT,
                    borderBottom: isBottomEdge ? "2px dashed #1976d2" : "1px solid #d0d0d0",
                    borderRight: isRightEdge ? "2px dashed #1976d2" : (ci < numCols - 1 ? "1px solid #d0d0d0" : "none"),
                    borderLeft: isLeftEdge ? "2px dashed #1976d2" : "none",
                    borderTop: isTopEdge ? "2px dashed #1976d2" : "none",
                    outline: isAnchor ? "2px solid var(--accent-primary)" : "none",
                    outlineOffset: -2,
                    background: cellBg,
                    padding: 0,
                    cursor: "cell",
                    position: "relative",
                    boxSizing: "border-box",
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
                        background: "#fff",
                        color: "#111",
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
                      color: cellColor,
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
        padding: "6px 0", marginTop: 0,
      }}>
        {/* Action toggles */}
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => onActionChange(action === "tokenize" ? "none" : "tokenize")}
            style={{
              flex: 1,
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
              borderRadius: 4,
              cursor: "pointer",
              border: action === "tokenize" ? "1px solid #9c27b0" : "1px solid transparent",
              background: action === "tokenize" ? "rgba(156,39,176,0.15)" : "transparent",
              color: "#9c27b0",
              boxShadow: action === "tokenize" ? "0 0 8px rgba(156,39,176,0.3)" : "none",
              textShadow: "none",
              transition: "all 0.15s ease",
            }}
            title="Flag matched regions for tokenization"
          >
            <Key size={13} />
            Tokenize
          </button>
          <button
            onClick={() => onActionChange(action === "remove" ? "none" : "remove")}
            style={{
              flex: 1,
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
              borderRadius: 4,
              cursor: "pointer",
              border: action === "remove" ? "1px solid #f44336" : "1px solid transparent",
              background: action === "remove" ? "rgba(244,67,54,0.15)" : "transparent",
              color: "#f44336",
              boxShadow: action === "remove" ? "0 0 8px rgba(244,67,54,0.3)" : "none",
              textShadow: "none",
              transition: "all 0.15s ease",
            }}
            title="Flag matched regions for removal"
          >
            <Trash2 size={13} />
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
