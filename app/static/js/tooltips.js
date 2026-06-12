(function () {
  const VIEWPORT_PAD = 8;

  let activeTip = null;
  let activePopover = null;

  function isInside(node, target) {
    return Boolean(target && node && (node === target || node.contains(target)));
  }

  function closePopover() {
    if (!activePopover || !activeTip) {
      return;
    }

    activePopover.classList.remove("is-open");
    activePopover.style.cssText = "";
    activeTip.appendChild(activePopover);
    activePopover = null;
    activeTip = null;
  }

  function positionPopover(tip, popover) {
    const rect = tip.getBoundingClientRect();
    popover.style.position = "fixed";
    popover.style.zIndex = "1000";
    popover.style.width = "max-content";
    popover.style.height = "auto";
    popover.style.bottom = "auto";
    popover.style.right = "auto";
    popover.style.pointerEvents = "auto";
    popover.style.left = "-9999px";
    popover.style.top = "0px";

    const popoverRect = popover.getBoundingClientRect();
    let left = rect.left + rect.width / 2 - popoverRect.width / 2;
    let top = rect.bottom + 6;

    if (left < VIEWPORT_PAD) {
      left = VIEWPORT_PAD;
    }
    if (left + popoverRect.width > window.innerWidth - VIEWPORT_PAD) {
      left = window.innerWidth - popoverRect.width - VIEWPORT_PAD;
    }
    if (top + popoverRect.height > window.innerHeight - VIEWPORT_PAD) {
      top = rect.top - popoverRect.height - 6;
    }
    if (top < VIEWPORT_PAD) {
      top = VIEWPORT_PAD;
    }

    popover.style.left = `${Math.round(left)}px`;
    popover.style.top = `${Math.round(top)}px`;
  }

  function openPopover(tip, popover) {
    if (activePopover === popover) {
      positionPopover(tip, popover);
      return;
    }

    closePopover();
    activeTip = tip;
    activePopover = popover;

    document.body.appendChild(popover);
    popover.classList.add("is-open");
    positionPopover(tip, popover);
  }

  function initPopoverTip(tip) {
    const popover = tip.querySelector(".info-popover");
    if (!popover) {
      return;
    }

    tip.addEventListener("mouseenter", () => openPopover(tip, popover));
    tip.addEventListener("focus", () => openPopover(tip, popover));

    tip.addEventListener("mouseleave", (event) => {
      if (isInside(popover, event.relatedTarget)) {
        return;
      }
      closePopover();
    });

    popover.addEventListener("mouseenter", () => openPopover(tip, popover));
    popover.addEventListener("mouseleave", (event) => {
      if (isInside(tip, event.relatedTarget)) {
        return;
      }
      closePopover();
    });

    tip.addEventListener("blur", (event) => {
      if (isInside(popover, event.relatedTarget)) {
        return;
      }
      closePopover();
    });
  }

  document.querySelectorAll(".info-tip--popover").forEach(initPopoverTip);
})();
