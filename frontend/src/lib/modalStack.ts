type ModalEntry = {
  id: string;
  onCloseRef: { current: () => void };
};

const stack: ModalEntry[] = [];
const subscribers = new Set<() => void>();
let escapeHandler: ((event: KeyboardEvent) => void) | null = null;

function notifySubscribers(): void {
  subscribers.forEach((callback) => callback());
}

function attachEscapeListener(): void {
  if (escapeHandler) return;

  escapeHandler = (event: KeyboardEvent) => {
    if (event.key === "Escape" && stack.length > 0) {
      event.preventDefault();
      event.stopPropagation();
      const topModal = stack[stack.length - 1];
      topModal.onCloseRef.current();
    }
  };

  window.addEventListener("keydown", escapeHandler, true);
}

function detachEscapeListener(): void {
  if (escapeHandler) {
    window.removeEventListener("keydown", escapeHandler, true);
    escapeHandler = null;
  }
}

export function pushModal(id: string, onCloseRef: { current: () => void }): void {
  const existing = stack.findIndex((entry) => entry.id === id);
  if (existing !== -1) return;

  stack.push({ id, onCloseRef });

  if (stack.length === 1) {
    const root = document.getElementById("root");
    if (root) {
      root.setAttribute("inert", "");
    }
    attachEscapeListener();
  }

  notifySubscribers();
}

export function popModal(id: string): void {
  const index = stack.findIndex((entry) => entry.id === id);
  if (index === -1) return;

  stack.splice(index, 1);

  if (stack.length === 0) {
    const root = document.getElementById("root");
    if (root) {
      root.removeAttribute("inert");
    }
    detachEscapeListener();
  }

  notifySubscribers();
}

export function isTopModal(id: string): boolean {
  return stack.length > 0 && stack[stack.length - 1].id === id;
}

export function getStackSize(): number {
  return stack.length;
}

export function subscribe(callback: () => void): () => void {
  subscribers.add(callback);
  return () => {
    subscribers.delete(callback);
  };
}

export function getSnapshot(): number {
  return stack.length;
}

export function isEscapeListenerAttached(): boolean {
  return escapeHandler !== null;
}

export function _resetForTesting(): void {
  stack.length = 0;
  subscribers.clear();
  detachEscapeListener();
  const root = document.getElementById("root");
  if (root) {
    root.removeAttribute("inert");
  }
}
