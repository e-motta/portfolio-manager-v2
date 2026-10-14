import { useEffect, useRef, useState } from "react";

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

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="action-menu" ref={menuRef}>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {trigger}
      </button>
      {open && (
        <div className="action-menu__dropdown" role="menu">
          {actions.map((action, index) => (
            <button
              key={index}
              type="button"
              className="action-menu__item"
              role="menuitem"
              onClick={() => {
                action.onClick();
                setOpen(false);
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
