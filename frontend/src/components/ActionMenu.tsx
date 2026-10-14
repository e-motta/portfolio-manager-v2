import { useEffect, useRef, useState, useCallback } from "react";

type Action = {
  label: string;
  onClick: () => void;
};

type ActionMenuProps = {
  trigger?: string;
  actions: Action[];
};

export function ActionMenu({ trigger = "More ⋯", actions }: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const closeMenu = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        closeMenu();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu();
        return;
      }

      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const items = itemsRef.current.filter(Boolean) as HTMLButtonElement[];
        const currentIndex = items.findIndex((item) => item === document.activeElement);
        let nextIndex: number;

        if (event.key === "ArrowDown") {
          nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
        } else {
          nextIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
        }

        items[nextIndex]?.focus();
      }

      if (event.key === "Tab") {
        closeMenu();
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    const firstItem = itemsRef.current[0];
    if (firstItem) {
      requestAnimationFrame(() => firstItem.focus());
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, closeMenu]);

  return (
    <div className="action-menu" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        className="btn btn--ghost"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {trigger}
      </button>
      {open && (
        <div className="action-menu__dropdown" role="menu" aria-label="Actions">
          {actions.map((action, index) => (
            <button
              key={index}
              ref={(el) => { itemsRef.current[index] = el; }}
              type="button"
              className="action-menu__item"
              role="menuitem"
              onClick={() => {
                action.onClick();
                closeMenu();
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
