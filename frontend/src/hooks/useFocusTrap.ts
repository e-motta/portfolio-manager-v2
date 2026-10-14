import { useEffect, useRef, useCallback } from "react";

const FOCUSABLE_SELECTOR = [
  'a[href]:not([disabled]):not([tabindex="-1"])',
  'button:not([disabled]):not([tabindex="-1"])',
  'input:not([disabled]):not([type="hidden"]):not([tabindex="-1"])',
  'select:not([disabled]):not([tabindex="-1"])',
  'textarea:not([disabled]):not([tabindex="-1"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
].join(",");

export function useFocusTrap(active: boolean, initialFocusRef?: React.RefObject<HTMLElement | null>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<Element | null>(null);

  const getFocusableElements = useCallback(() => {
    if (!containerRef.current) return [];
    return Array.from(containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter((el) => el.offsetParent !== null);
  }, []);

  useEffect(() => {
    if (!active) return;

    previousActiveElement.current = document.activeElement;

    const initialFocusTarget = initialFocusRef?.current;
    if (initialFocusTarget) {
      requestAnimationFrame(() => initialFocusTarget.focus());
    } else {
      const focusable = getFocusableElements();
      if (focusable.length > 0) {
        requestAnimationFrame(() => focusable[0].focus());
      }
    }

    return () => {
      if (previousActiveElement.current instanceof HTMLElement) {
        previousActiveElement.current.focus();
      }
    };
  }, [active, initialFocusRef, getFocusableElements]);

  useEffect(() => {
    if (!active) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Tab") return;

      const focusable = getFocusableElements();
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [active, getFocusableElements]);

  return containerRef;
}

export function useInert(active: boolean, excludeSelector?: string) {
  useEffect(() => {
    if (!active) return;

    const elements = document.querySelectorAll<HTMLElement>("body > *");
    const excluded = excludeSelector ? document.querySelectorAll(excludeSelector) : [];
    const excludedSet = new Set(excluded);
    const inertedElements: HTMLElement[] = [];

    elements.forEach((el) => {
      if (!excludedSet.has(el) && !el.hasAttribute("inert")) {
        el.setAttribute("inert", "");
        inertedElements.push(el);
      }
    });

    return () => {
      inertedElements.forEach((el) => el.removeAttribute("inert"));
    };
  }, [active, excludeSelector]);
}
