type ModalEntry = {
  id: string;
  onClose: () => void;
};

const stack: ModalEntry[] = [];

export function pushModal(id: string, onClose: () => void): void {
  stack.push({ id, onClose });
  
  if (stack.length === 1) {
    const root = document.getElementById("root");
    if (root) {
      root.setAttribute("inert", "");
    }
  }
}

export function popModal(id: string): void {
  const index = stack.findIndex((entry) => entry.id === id);
  if (index !== -1) {
    stack.splice(index, 1);
  }
  
  if (stack.length === 0) {
    const root = document.getElementById("root");
    if (root) {
      root.removeAttribute("inert");
    }
  }
}

export function isTopModal(id: string): boolean {
  return stack.length > 0 && stack[stack.length - 1].id === id;
}

export function getStackSize(): number {
  return stack.length;
}

export function handleEscape(): boolean {
  if (stack.length === 0) return false;
  
  const topModal = stack[stack.length - 1];
  topModal.onClose();
  return true;
}

let escapeListenerAttached = false;

export function attachEscapeListener(): void {
  if (escapeListenerAttached) return;
  
  const handler = (event: KeyboardEvent) => {
    if (event.key === "Escape" && stack.length > 0) {
      event.preventDefault();
      event.stopPropagation();
      handleEscape();
    }
  };
  
  window.addEventListener("keydown", handler, true);
  escapeListenerAttached = true;
}

export function _resetForTesting(): void {
  stack.length = 0;
  const root = document.getElementById("root");
  if (root) {
    root.removeAttribute("inert");
  }
}
