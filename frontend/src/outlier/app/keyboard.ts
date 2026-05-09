export type KeyboardShortcuts = {
  selectNext: () => void;
  selectPrevious: () => void;
  openSelected: () => void;
  closeRail: () => void;
  focusSearch: () => void;
};

export function registerKeyboardShortcuts(callbacks: KeyboardShortcuts) {
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isTyping = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
    if (event.key === "/" && !isTyping) {
      event.preventDefault();
      callbacks.focusSearch();
      return;
    }
    if (isTyping) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      callbacks.selectNext();
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      callbacks.selectPrevious();
    }
    if (event.key === "Enter") {
      event.preventDefault();
      callbacks.openSelected();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      callbacks.closeRail();
    }
  });
}
