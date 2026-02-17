/** Excel-like grid for blacklist term entry with copy/paste support. */

import { useState, useCallback, useRef, useEffect } from "react";
import { Key, Trash2 } from "lucide-react";
import { MAX_COLS, MAX_ROWS } from "./blacklistUtils";

/** Marching ants keyframes – injected once. */
const MARCHING_ANTS_STYLE = `
@keyframes marchTop    { from { background-position-x: 0; }   to { background-position-x: 8px; } }
@keyframes marchRight  { from { background-position-y: 0; }   to { background-position-y: 8px; } }
@keyframes marchBottom { from { background-position-x: 0; }   to { background-position-x: -8px; } }
@keyframes marchLeft   { from { background-position-y: 0; }   to { background-position-y: -8px; } }
.march-top    { background: repeating-linear-gradient(90deg, #1976d2 0 4px, transparent 4px 8px) top/100% 1px no-repeat;    animation: marchTop 0.3s linear infinite; }
.march-bottom { background: repeating-linear-gradient(90deg, #1976d2 0 4px, transparent 4px 8px) bottom/100% 1px no-repeat; animation: marchBottom 0.3s linear infinite; }
.march-left   { background: repeating-linear-gradient(180deg, #1976d2 0 4px, transparent 4px 8px) left/1px 100% no-repeat;  animation: marchLeft 0.3s linear infinite; }
.march-right  { background: repeating-linear-gradient(180deg, #1976d2 0 4px, transparent 4px 8px) right/1px 100% no-repeat; animation: marchRight 0.3s linear infinite; }
`;

const DEFAULT_COLS = 3;
const DEFAULT_VISIBLE_ROWS = 10;
const CELL_HEIGHT = 28;
const CELL_MIN_WIDTH = 40;

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
  const formulaInputRef = useRef<HTMLInputElement>(null);
  const resizeRef = useRef<{ col: number; startX: number; startWidth: number } | null>(null);
  const [dragMoveOrigin, setDragMoveOrigin] = useState<{ row: number; col: number } | null>(null);

  const [colWidths, setColWidths] = useState<number[]>(() => Array(cells[0]?.length ?? DEFAULT_COLS).fill(80));
  const [isDragMoving, setIsDragMoving] = useState(false);
  const [dragMoveTarget, setDragMoveTarget] = useState<{ row: number; col: number } | null>(null);

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
    if ((e.ctrlKey || e.metaKey) && ["c", "v", "x", "a", "z", "y"].includes(e.key.toLowerCase())) {
      e.stopPropagation();
      const key = e.key.toLowerCase();
      // Ctrl+A: select all cells in the grid
      if (key === "a") {
        e.preventDefault();
        setSelectedCell({ row: 0, col: 0 });
        setSelectionEnd({ row: numRows - 1, col: numCols - 1 });
        setEditingCell(null);
      }
      // Ctrl+Z: undo
      if (key === "z") {
        e.preventDefault();
        handleUndo();
      }
      // Ctrl+Y: redo
      if (key === "y") {
        e.preventDefault();
        handleRedo();
      }
      // Ctrl+X: cut — copy selection to clipboard then clear
      if (key === "x" && !editingCell && selectedCell) {
        e.preventDefault();
        const bounds = getSelectionBounds();
        if (bounds) {
          const lines: string[] = [];
          for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
            const rowCells: string[] = [];
            for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
              rowCells.push(cells[r]?.[c] ?? "");
            }
            lines.push(rowCells.join("\t"));
          }
          navigator.clipboard.writeText(lines.join("\n"));
          setCopiedBounds(bounds);
          // Clear cells in selection
          pushUndo();
          const next = cells.map(r => [...r]);
          for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
            for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
              if (next[r]) next[r][c] = "";
            }
          }
          onCellsChange(next);
        }
      }
      // Ctrl+C and Ctrl+V: let native events fire (handled by onCopy/onPaste)
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
        // Restore focus to grid so keyboard navigation continues
        requestAnimationFrame(() => gridRef.current?.focus());
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
      // Ctrl+Arrow: jump to next cell boundary (empty↔filled transition), like Excel
      if (e.key === "ArrowUp") {
        let newRow: number;
        if (e.ctrlKey || e.metaKey) {
          const fromRow = e.shiftKey ? anchor.row : row;
          const cur = (cells[fromRow]?.[col] ?? "").trim();
          newRow = 0;
          if (cur === "") {
            // Jump to nearest non-empty cell above
            for (let r = fromRow - 1; r >= 0; r--) {
              if ((cells[r]?.[col] ?? "").trim() !== "") { newRow = r; break; }
            }
          } else {
            // Jump to top of contiguous filled block, or next filled cell above a gap
            for (let r = fromRow - 1; r >= 0; r--) {
              if ((cells[r]?.[col] ?? "").trim() === "") { newRow = r + 1; break; }
            }
          }
        } else {
          newRow = Math.max(0, (e.shiftKey ? anchor.row : row) - 1);
        }
        if (e.shiftKey) setSelectionEnd({ row: newRow, col: anchor.col });
        else { setSelectedCell({ row: newRow, col }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowDown") {
        let newRow: number;
        if (e.ctrlKey || e.metaKey) {
          const fromRow = e.shiftKey ? anchor.row : row;
          const cur = (cells[fromRow]?.[col] ?? "").trim();
          newRow = numRows - 1;
          if (cur === "") {
            for (let r = fromRow + 1; r < numRows; r++) {
              if ((cells[r]?.[col] ?? "").trim() !== "") { newRow = r; break; }
            }
          } else {
            for (let r = fromRow + 1; r < numRows; r++) {
              if ((cells[r]?.[col] ?? "").trim() === "") { newRow = r - 1; break; }
            }
          }
        } else {
          newRow = Math.min(numRows - 1, (e.shiftKey ? anchor.row : row) + 1);
        }
        if (e.shiftKey) setSelectionEnd({ row: newRow, col: anchor.col });
        else { setSelectedCell({ row: newRow, col }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowLeft") {
        let newCol: number;
        if (e.ctrlKey || e.metaKey) {
          const fromCol = e.shiftKey ? anchor.col : col;
          const cur = (cells[row]?.[fromCol] ?? "").trim();
          newCol = 0;
          if (cur === "") {
            for (let c = fromCol - 1; c >= 0; c--) {
              if ((cells[row]?.[c] ?? "").trim() !== "") { newCol = c; break; }
            }
          } else {
            for (let c = fromCol - 1; c >= 0; c--) {
              if ((cells[row]?.[c] ?? "").trim() === "") { newCol = c + 1; break; }
            }
          }
        } else {
          newCol = Math.max(0, (e.shiftKey ? anchor.col : col) - 1);
        }
        if (e.shiftKey) setSelectionEnd({ row: anchor.row, col: newCol });
        else { setSelectedCell({ row, col: newCol }); setSelectionEnd(null); }
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === "ArrowRight") {
        let newCol: number;
        if (e.ctrlKey || e.metaKey) {
          const fromCol = e.shiftKey ? anchor.col : col;
          const cur = (cells[row]?.[fromCol] ?? "").trim();
          newCol = numCols - 1;
          if (cur === "") {
            for (let c = fromCol + 1; c < numCols; c++) {
              if ((cells[row]?.[c] ?? "").trim() !== "") { newCol = c; break; }
            }
          } else {
            for (let c = fromCol + 1; c < numCols; c++) {
              if ((cells[row]?.[c] ?? "").trim() === "") { newCol = c - 1; break; }
            }
          }
        } else {
          newCol = Math.min(numCols - 1, (e.shiftKey ? anchor.col : col) + 1);
        }
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
  }, [numRows]);

  // Select entire row
  const selectRow = useCallback((row: number) => {
    setSelectedCell({ row, col: 0 });
    setSelectionEnd({ row, col: numCols - 1 });
    setEditingCell(null);
  }, [numCols]);

  // Column resize handler — first fills available space, then shrinks others
  const handleResizeStart = useCallback((col: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = { col, startX: e.clientX, startWidth: colWidths[col] };
    const snapshotWidths = [...colWidths];
    // Measure available container width (subtract row-number gutter + scrollbar margin)
    const containerWidth = gridRef.current ? gridRef.current.clientWidth - 32 - 2 : 0;
    const handleResizeMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = ev.clientX - resizeRef.current.startX;
      const newWidth = Math.max(CELL_MIN_WIDTH, resizeRef.current.startWidth + delta);
      const actualDelta = newWidth - snapshotWidths[col];
      if (actualDelta === 0) {
        setColWidths([...snapshotWidths]);
        return;
      }
      const next = [...snapshotWidths];
      next[col] = newWidth;

      if (actualDelta > 0 && containerWidth > 0) {
        // Calculate how much total width all columns currently use
        const totalBefore = snapshotWidths.reduce((s, w) => s + w, 0);
        const freeSpace = Math.max(0, containerWidth - totalBefore);
        // First, consume free space
        const absorbed = Math.min(freeSpace, actualDelta);
        const excess = actualDelta - absorbed;
        // Only shrink others by the excess that doesn't fit in free space
        if (excess > 0) {
          const others = next.map((_w, i) => i !== col ? i : -1).filter(i => i >= 0);
          const totalOther = others.reduce((s, i) => s + snapshotWidths[i], 0);
          let remaining = excess;
          for (const i of others) {
            const share = totalOther > 0 ? (snapshotWidths[i] / totalOther) * excess : excess / others.length;
            const shrunk = Math.max(CELL_MIN_WIDTH, snapshotWidths[i] - share);
            const taken = snapshotWidths[i] - shrunk;
            next[i] = shrunk;
            remaining -= taken;
          }
          // If we couldn't take enough from others, clamp the resized col
          if (remaining > 0.5) {
            next[col] = newWidth - remaining;
          }
        }
      }
      setColWidths(next);
    };
    const handleResizeEnd = () => {
      resizeRef.current = null;
      window.removeEventListener("mousemove", handleResizeMove);
      window.removeEventListener("mouseup", handleResizeEnd);
    };
    window.addEventListener("mousemove", handleResizeMove);
    window.addEventListener("mouseup", handleResizeEnd);
  }, [colWidths]);

  // Drag-move preview bounds
  const getDragMovePreviewBounds = useCallback(() => {
    if (!isDragMoving || !dragMoveTarget || !dragMoveOrigin) return null;
    const bounds = getSelectionBounds();
    if (!bounds) return null;
    const origin = dragMoveOrigin;
    const deltaRow = dragMoveTarget.row - origin.row;
    const deltaCol = dragMoveTarget.col - origin.col;
    return {
      minRow: bounds.minRow + deltaRow,
      maxRow: bounds.maxRow + deltaRow,
      minCol: bounds.minCol + deltaCol,
      maxCol: bounds.maxCol + deltaCol,
    };
  }, [isDragMoving, dragMoveTarget, dragMoveOrigin, getSelectionBounds]);

  const isInDragPreview = useCallback((row: number, col: number) => {
    const preview = getDragMovePreviewBounds();
    if (!preview) return false;
    return row >= preview.minRow && row <= preview.maxRow && col >= preview.minCol && col <= preview.maxCol;
  }, [getDragMovePreviewBounds]);

  // Mouse drag handlers for range selection
  const handleCellMouseDown = useCallback((row: number, col: number, e: React.MouseEvent) => {
    if (e.shiftKey && selectedCell) {
      setSelectionEnd({ row, col });
    } else if (selectionEnd && isInSelection(row, col)) {
      // Clicked inside multi-cell selection — start drag-move
      setIsDragMoving(true);
      setDragMoveOrigin({ row, col });
    } else if (!selectionEnd && selectedCell && selectedCell.row === row && selectedCell.col === col && !editingCell) {
      // Clicked the single selected cell again — start drag-move for single cell
      setIsDragMoving(true);
      setDragMoveOrigin({ row, col });
    } else {
      setSelectedCell({ row, col });
      setSelectionEnd(null);
      setIsDragging(true);
    }
    setEditingCell(null);
  }, [selectedCell, selectionEnd, editingCell, isInSelection]);

  const handleCellMouseEnter = useCallback((row: number, col: number) => {
    if (isDragging) {
      setSelectionEnd({ row, col });
    } else if (isDragMoving) {
      setDragMoveTarget({ row, col });
    }
  }, [isDragging, isDragMoving]);

  const handleMouseUp = useCallback(() => {
    if (isDragMoving && dragMoveTarget && dragMoveOrigin) {
      const bounds = getSelectionBounds();
      if (bounds) {
        const origin = dragMoveOrigin;
        const deltaRow = dragMoveTarget.row - origin.row;
        const deltaCol = dragMoveTarget.col - origin.col;
        if (deltaRow !== 0 || deltaCol !== 0) {
          const newMinRow = bounds.minRow + deltaRow;
          const newMaxRow = bounds.maxRow + deltaRow;
          const newMinCol = bounds.minCol + deltaCol;
          const newMaxCol = bounds.maxCol + deltaCol;
          if (newMinRow >= 0 && newMaxRow < MAX_ROWS && newMinCol >= 0 && newMaxCol < MAX_COLS) {
            pushUndo();
            const next = cells.map(r => [...r]);
            const values: string[][] = [];
            for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
              const rowVals: string[] = [];
              for (let c = bounds.minCol; c <= bounds.maxCol; c++) {
                rowVals.push(next[r]?.[c] ?? "");
                next[r][c] = "";
              }
              values.push(rowVals);
            }
            for (let r = 0; r < values.length; r++) {
              for (let c = 0; c < values[r].length; c++) {
                next[newMinRow + r][newMinCol + c] = values[r][c];
              }
            }
            onCellsChange(next);
            setSelectedCell({ row: newMinRow, col: newMinCol });
            setSelectionEnd({ row: newMaxRow, col: newMaxCol });
          }
        }
      }
    }
    setIsDragging(false);
    setIsDragMoving(false);
    setDragMoveTarget(null);
    setDragMoveOrigin(null);
  }, [isDragMoving, dragMoveOrigin, dragMoveTarget, getSelectionBounds, cells, onCellsChange, pushUndo]);

  // Global mouseup listener for drag end
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      setIsDragging(false);
      setIsDragMoving(false);
      setDragMoveTarget(null);
      setDragMoveOrigin(null);
    };
    window.addEventListener("mouseup", handleGlobalMouseUp);
    return () => window.removeEventListener("mouseup", handleGlobalMouseUp);
  }, []);

  const filledCellCount = cells.flat().filter(c => c.trim().length > 0).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minHeight: 0 }}>
      {/* Inject marching ants animation */}
      <style dangerouslySetInnerHTML={{ __html: MARCHING_ANTS_STYLE }} />
      {/* Formula bar */}
      <div style={{
        display: "flex", alignItems: "center",
        height: 26,
        border: "1px solid var(--border-color)",
        borderRadius: 4,
        overflow: "hidden",
        background: "#fff",
        fontSize: 12,
        flexShrink: 0,
      }}>
        <div style={{
          width: 44, minWidth: 44,
          height: "100%",
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "#e8eef4",
          borderRight: "1px solid var(--border-color)",
          fontWeight: 600,
          color: "#1a4971",
          fontSize: 11,
        }}>
          {selectedCell ? `${String.fromCharCode(65 + selectedCell.col)}${selectedCell.row + 1}` : ""}
        </div>
        <input
          ref={formulaInputRef}
          value={selectedCell ? cells[selectedCell.row]?.[selectedCell.col] ?? "" : ""}
          onChange={(e) => {
            if (selectedCell) {
              updateCell(selectedCell.row, selectedCell.col, e.target.value);
            }
          }}
          onFocus={() => { if (selectedCell) pushUndo(); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "Escape") {
              e.preventDefault();
              gridRef.current?.focus();
            }
            e.stopPropagation();
          }}
          style={{
            flex: 1, height: "100%",
            border: "none", outline: "none",
            padding: "0 8px",
            fontSize: 12, fontFamily: "inherit",
            background: "transparent", color: "#111",
          }}
          readOnly={!selectedCell}
        />
      </div>

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
            background: "#e8eef4",
            borderBottom: "1px solid #a8c5e0",
            borderRight: "1px solid #a8c5e0",
          }} />
          {Array.from({ length: numCols }, (_, ci) => (
            <div
              key={ci}
              onClick={() => selectColumn(ci)}
              style={{
                width: colWidths[ci], minWidth: CELL_MIN_WIDTH, height: 24,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, fontWeight: 600,
                color: "#1a4971",
                background: "#e8eef4",
                borderBottom: "1px solid #a8c5e0",
                borderRight: ci < numCols - 1 ? "1px solid #a8c5e0" : "none",
                cursor: "pointer",
                position: "relative",
                userSelect: "none",
              }}
            >
              {String.fromCharCode(65 + ci)}
              {/* Resize handle */}
              <div
                onMouseDown={(e) => handleResizeStart(ci, e)}
                style={{
                  position: "absolute",
                  right: -2, top: 0,
                  width: 5, height: "100%",
                  cursor: "col-resize",
                  zIndex: 2,
                }}
              />
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
                background: "#e8eef4",
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
              const inDragPreview = isInDragPreview(ri, ci);
              const isEditing = editingCell?.row === ri && editingCell?.col === ci;
              const key = `${ri},${ci}`;
              const status = matchStatus?.get(key);
              let cellBg = "#ffffff";
              let cellColor = cellVal ? "#111" : "#999";
              if (status === "matched") { cellBg = "#e8f5e9"; cellColor = "#2e7d32"; }
              else if (status === "no-match") { cellBg = "#fff3e0"; cellColor = "#e65100"; }
              else if (status === "exists") { cellBg = "#e3f2fd"; cellColor = "#1565c0"; }
              // Override bg for drag preview
              if (inDragPreview) { cellBg = "#ffffff"; }
              // Override bg for selection (overrides match status)
              if (inSelection) { cellBg = "#cce5ff"; cellColor = "#111"; }

              // Determine if this cell needs marching-ants overlay on any edge
              const isLeftEdge = inCopied && ci === copiedBounds?.minCol;
              const isTopEdge = inCopied && ri === copiedBounds?.minRow;
              const isRightEdge = inCopied && ci === copiedBounds?.maxCol;
              const isBottomEdge = inCopied && ri === copiedBounds?.maxRow;
              const hasCopiedEdge = isLeftEdge || isTopEdge || isRightEdge || isBottomEdge;

              // Drag preview border edges
              const previewBounds = getDragMovePreviewBounds();
              const isPLeft = inDragPreview && ci === previewBounds?.minCol;
              const isPTop = inDragPreview && ri === previewBounds?.minRow;
              const isPRight = inDragPreview && ci === previewBounds?.maxCol;
              const isPBottom = inDragPreview && ri === previewBounds?.maxRow;
              const hasPreviewEdge = isPLeft || isPTop || isPRight || isPBottom;

              return (
                <div
                  key={ci}
                  onMouseDown={(e) => handleCellMouseDown(ri, ci, e)}
                  onMouseEnter={() => handleCellMouseEnter(ri, ci)}
                  onMouseUp={handleMouseUp}
                  onDoubleClick={() => setEditingCell({ row: ri, col: ci })}
                  style={{
                    width: colWidths[ci], minWidth: CELL_MIN_WIDTH, height: CELL_HEIGHT,
                    borderBottom: "1px solid #d0d0d0",
                    borderRight: ci < numCols - 1 ? "1px solid #d0d0d0" : "none",
                    borderLeft: "none",
                    borderTop: "none",
                    outline: isAnchor ? "2px solid var(--accent-primary)" : "none",
                    outlineOffset: -2,
                    background: cellBg,
                    padding: 0,
                    cursor: isDragMoving ? "grabbing" : ((isAnchor && !editingCell && cellVal) || (inSelection && selectionEnd && !editingCell)) ? "grab" : "cell",
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
                  {/* Marching ants overlay for copied / drag-preview edges */}
                  {(hasCopiedEdge || hasPreviewEdge) && (
                    <>
                      {(isTopEdge || isPTop) && <div className="march-top" style={{ position: "absolute", top: -1, left: 0, right: 0, height: 1, pointerEvents: "none" }} />}
                      {(isBottomEdge || isPBottom) && <div className="march-bottom" style={{ position: "absolute", bottom: -1, left: 0, right: 0, height: 1, pointerEvents: "none" }} />}
                      {(isLeftEdge || isPLeft) && <div className="march-left" style={{ position: "absolute", left: -1, top: 0, bottom: 0, width: 1, pointerEvents: "none" }} />}
                      {(isRightEdge || isPRight) && <div className="march-right" style={{ position: "absolute", right: -1, top: 0, bottom: 0, width: 1, pointerEvents: "none" }} />}
                    </>
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
