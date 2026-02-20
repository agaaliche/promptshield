import React from "react";

interface IconProps extends React.HTMLAttributes<HTMLElement> {
  size?: number;
  color?: string;
  strokeWidth?: number; // ignored - kept for lucide-react compat
  /** Override the FA family, e.g. "light" renders fa-light instead of the default. */
  variant?: "duotone" | "light" | "solid" | "regular" | "thin";
}

/**
 * Factory that returns a React component rendering an <i> element
 * with the given Font Awesome class string.
 * Accepts the same common props that lucide-react icons did (size, color, className...).
 */
const faIcon = (faClass: string, displayName: string) => {
  const Icon: React.FC<IconProps> = ({
    size,
    color,
    className = "",
    style,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    strokeWidth: _sw,
    variant,
    ...rest
  }) => {
    let cls = faClass;
    if (variant) {
      cls = cls.replace(/fa-(duotone|solid|regular|light|thin)\b/, `fa-${variant}`);
    }
    return (
      <i
        className={`${cls} ${className}`.trim()}
        style={{ fontSize: size, color, ...style }}
        {...rest}
      />
    );
  };
  Icon.displayName = displayName;
  return Icon;
};

/* --- Exported icon components ----------------------------------- */

export const AlertCircle = faIcon("fa-duotone fa-circle-exclamation", "AlertCircle");
export const AlertTriangle = faIcon("fa-duotone fa-triangle-exclamation", "AlertTriangle");
export const ArrowLeft = faIcon("fa-duotone fa-arrow-left", "ArrowLeft");
export const ArrowRight = faIcon("fa-duotone fa-arrow-right", "ArrowRight");
export const ArrowRightLeft = faIcon("fa-duotone fa-right-left-large", "ArrowRightLeft");
export const ArrowUpCircle = faIcon("fa-duotone fa-circle-arrow-up", "ArrowUpCircle");
export const ArrowUpDown = faIcon("fa-duotone fa-arrows-up-down", "ArrowUpDown");
export const BoxSelect = faIcon("fa-light fa-object-group", "BoxSelect");
export const BullseyePointer = faIcon("fa-duotone fa-bullseye-pointer", "BullseyePointer");
export const Brain = faIcon("fa-duotone fa-brain", "Brain");
export const Check = faIcon("fa-duotone fa-check", "Check");
export const CheckCircle = faIcon("fa-duotone fa-circle-check", "CheckCircle");
export const CheckCircle2 = faIcon("fa-duotone fa-circle-check", "CheckCircle2");
export const ChevronDown = faIcon("fa-duotone fa-chevron-down", "ChevronDown");
export const ChevronLeft = faIcon("fa-duotone fa-chevron-left", "ChevronLeft");
export const ChevronRight = faIcon("fa-duotone fa-chevron-right", "ChevronRight");
export const ChevronsLeft = faIcon("fa-duotone fa-angles-left", "ChevronsLeft");
export const ChevronsRight = faIcon("fa-duotone fa-angles-right", "ChevronsRight");
export const Clock = faIcon("fa-light fa-clock", "Clock");
export const Copy = faIcon("fa-light fa-copy", "Copy");
export const Cpu = faIcon("fa-duotone fa-microchip", "Cpu");
export const Database = faIcon("fa-duotone fa-database", "Database");
export const Download = faIcon("fa-duotone fa-download", "Download");
export const Edit3 = faIcon("fa-duotone fa-pen", "Edit3");
export const ExternalLink = faIcon("fa-duotone fa-arrow-up-right-from-square", "ExternalLink");
export const FileSearch = faIcon("fa-duotone fa-file-magnifying-glass", "FileSearch");
export const FileShield = faIcon("fa-duotone fa-file-shield", "FileShield");
export const FileText = faIcon("fa-duotone fa-file-lines", "FileText");
export const FolderOpen = faIcon("fa-duotone fa-folder-open", "FolderOpen");
export const FolderUp = faIcon("fa-duotone fa-folder-arrow-up", "FolderUp");
export const Globe = faIcon("fa-duotone fa-globe", "Globe");
export const Key = faIcon("fa-duotone fa-key", "Key");
export const LayoutGrid = faIcon("fa-duotone fa-grid-2", "LayoutGrid");
export const Loader2 = faIcon("fa-duotone fa-spinner fa-spin", "Loader2");
export const Lock = faIcon("fa-duotone fa-lock", "Lock");
export const LogOut = faIcon("fa-duotone fa-right-from-bracket", "LogOut");
export const Maximize2 = faIcon("fa-duotone fa-expand", "Maximize2");
export const Minimize2 = faIcon("fa-duotone fa-compress", "Minimize2");
export const MoreVertical = faIcon("fa-duotone fa-ellipsis-vertical", "MoreVertical");
export const MousePointer = faIcon("fa-duotone fa-arrow-pointer", "MousePointer");
export const Package = faIcon("fa-duotone fa-box", "Package");
export const PenTool = faIcon("fa-duotone fa-pen-fancy", "PenTool");
export const Pin = faIcon("fa-duotone fa-thumbtack", "Pin");
export const Play = faIcon("fa-duotone fa-play", "Play");
export const Plus = faIcon("fa-duotone fa-plus", "Plus");
export const Redo2 = faIcon("fa-duotone fa-rotate-right", "Redo2");
export const RefreshCw = faIcon("fa-duotone fa-arrows-rotate", "RefreshCw");
export const ReplaceAll = faIcon("fa-duotone fa-right-left", "ReplaceAll");
export const Save = faIcon("fa-duotone fa-floppy-disk", "Save");
export const ScanSearch = faIcon("fa-duotone fa-radar", "ScanSearch");
export const Scissors = faIcon("fa-duotone fa-scissors", "Scissors");
export const Search = faIcon("fa-duotone fa-magnifying-glass", "Search");
export const Settings = faIcon("fa-duotone fa-gear", "Settings");
export const Shield = faIcon("fa-duotone fa-shield-halved", "Shield");
export const ShieldSolid = faIcon("fa-solid fa-shield", "ShieldSolid");
export const ShieldCheck = faIcon("fa-duotone fa-shield-check", "ShieldCheck");
export const SlidersHorizontal = faIcon("fa-duotone fa-sliders", "SlidersHorizontal");
export const Sparkles = faIcon("fa-duotone fa-sparkles", "Sparkles");
export const Tag = faIcon("fa-duotone fa-tag", "Tag");
export const ToggleLeft = faIcon("fa-duotone fa-toggle-off", "ToggleLeft");
export const ToggleRight = faIcon("fa-duotone fa-toggle-on", "ToggleRight");
export const Trash2 = faIcon("fa-duotone fa-trash", "Trash2");
export const Undo2 = faIcon("fa-duotone fa-rotate-left", "Undo2");
export const Unlock = faIcon("fa-duotone fa-unlock", "Unlock");
export const Upload = faIcon("fa-duotone fa-upload", "Upload");
export const User = faIcon("fa-duotone fa-user", "User");
export const X = faIcon("fa-duotone fa-xmark", "X");
export const Zap = faIcon("fa-duotone fa-bolt", "Zap");
export const ZoomIn = faIcon("fa-light fa-magnifying-glass-plus", "ZoomIn");
export const ZoomOut = faIcon("fa-light fa-magnifying-glass-minus", "ZoomOut");