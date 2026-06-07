/** Helpers for turning a DOM text selection into a Reference + positioning popovers. */

export interface SelectionInfo {
  text: string;
  rect: DOMRect | null;
}

/** The current non-collapsed window selection, or null. */
export function getActiveSelection(): SelectionInfo | null {
  if (typeof window === 'undefined') return null;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const text = sel.toString().trim();
  if (!text) return null;
  let rect: DOMRect | null = null;
  try {
    rect = sel.getRangeAt(0).getBoundingClientRect();
  } catch {
    rect = null;
  }
  return { text, rect };
}

/** Whether the current selection is contained inside `el`. */
export function selectionInside(el: HTMLElement | null): boolean {
  if (!el || typeof window === 'undefined') return false;
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return false;
  const node = sel.getRangeAt(0).commonAncestorContainer;
  const element = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  return Boolean(element && el.contains(element));
}

export function truncatePreview(text: string, max = 280): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

/** Clamp a popover position near a selection rect so it stays inside the viewport. */
export function popoverPosition(
  rect: { left: number; top: number; bottom: number } | null,
  width = 320,
  height = 136,
): { left: number; top: number } {
  if (typeof window === 'undefined' || !rect) return { left: 16, top: 16 };
  const margin = 8;
  let top = rect.bottom + margin; // prefer below the selection
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - height - margin); // flip above if no room
  }
  const left = Math.min(Math.max(margin, rect.left), window.innerWidth - width - margin);
  return { left, top };
}
