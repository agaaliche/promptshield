import { useState, useRef, useEffect, useCallback } from 'react';

interface Position {
  x: number;
  y: number;
}

interface UseDraggableToolbarOptions {
  storageKey: string;
  defaultPos: Position;
  toolbarRef: React.RefObject<HTMLElement | null>;
  boundaryRef: React.RefObject<HTMLElement | null>;
  sidebarRef: React.RefObject<HTMLElement | null>;
  sidebarCollapsed: boolean;
}

interface UseDraggableToolbarResult {
  pos: Position;
  isDragging: boolean;
  startDrag: (e: React.MouseEvent) => void;
  constrainToArea: () => void;
}

const PAD = 8;

export default function useDraggableToolbar({
  storageKey,
  defaultPos,
  toolbarRef,
  boundaryRef,
  sidebarRef,
  sidebarCollapsed,
}: UseDraggableToolbarOptions): UseDraggableToolbarResult {
  const [pos, setPos] = useState<Position>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) return JSON.parse(saved);
    } catch {}
    return defaultPos;
  });

  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });

  const clamp = useCallback(
    (raw: Position): Position => {
      const tb = toolbarRef.current;
      const area = boundaryRef.current;
      if (!tb || !area) return raw;
      const areaRect = area.getBoundingClientRect();
      const sbWidth = sidebarRef.current?.offsetWidth ?? (sidebarCollapsed ? 60 : 320);
      const minX = areaRect.left + PAD;
      const minY = areaRect.top + PAD;
      const maxX = areaRect.right - sbWidth - tb.offsetWidth - PAD;
      const maxY = areaRect.bottom - tb.offsetHeight - PAD;
      return {
        x: Math.max(minX, Math.min(maxX, raw.x)),
        y: Math.max(minY, Math.min(maxY, raw.y)),
      };
    },
    [toolbarRef, boundaryRef, sidebarRef, sidebarCollapsed],
  );

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const dx = e.clientX - dragStart.current.mouseX;
      const dy = e.clientY - dragStart.current.mouseY;
      setPos(
        clamp({
          x: dragStart.current.startX + dx,
          y: dragStart.current.startY + dy,
        }),
      );
    };
    const handleMouseUp = () => {
      setIsDragging(false);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, clamp]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(pos));
    } catch {}
  }, [storageKey, pos]);

  const startDrag = useCallback(
    (e: React.MouseEvent) => {
      dragStart.current = {
        mouseX: e.clientX,
        mouseY: e.clientY,
        startX: pos.x,
        startY: pos.y,
      };
      setIsDragging(true);
    },
    [pos],
  );

  const constrainToArea = useCallback(() => {
    setPos((prev) => clamp(prev));
  }, [clamp]);

  return { pos, isDragging, startDrag, constrainToArea };
}
