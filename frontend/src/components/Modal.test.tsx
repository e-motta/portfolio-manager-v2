import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "./Modal";
import { useState } from "react";
import { _resetForTesting } from "../lib/modalStack";

function TestModalWithForm({ onSave }: { onSave: (value: string) => void }) {
  const [open, setOpen] = useState(true);
  const [value, setValue] = useState("");

  return (
    <Modal
      open={open}
      title="Test Modal"
      onClose={() => setOpen(false)}
      footer={
        <>
          <button type="button" onClick={() => setOpen(false)}>
            Cancel
          </button>
          <button type="button" onClick={() => onSave(value)}>
            Save
          </button>
        </>
      }
    >
      <label>
        Name
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          data-testid="modal-input"
        />
      </label>
    </Modal>
  );
}

function NestedModalsTest() {
  const [modalAOpen, setModalAOpen] = useState(true);
  const [modalBOpen, setModalBOpen] = useState(false);

  return (
    <>
      <Modal
        open={modalAOpen}
        title="Modal A"
        onClose={() => setModalAOpen(false)}
        footer={
          <button type="button" onClick={() => setModalBOpen(true)} data-testid="open-modal-b">
            Open Modal B
          </button>
        }
      >
        <p>Content A</p>
        <input type="text" data-testid="input-a" />
      </Modal>
      <Modal
        open={modalBOpen}
        title="Modal B"
        onClose={() => setModalBOpen(false)}
      >
        <p>Content B</p>
        <input type="text" data-testid="input-b" />
      </Modal>
    </>
  );
}

describe("Modal", () => {
  let rootEl: HTMLDivElement;

  beforeEach(() => {
    rootEl = document.createElement("div");
    rootEl.id = "root";
    document.body.appendChild(rootEl);
    _resetForTesting();
  });

  afterEach(() => {
    cleanup();
    _resetForTesting();
    rootEl.remove();
    const backdrops = document.querySelectorAll(".modal-backdrop");
    backdrops.forEach((b) => b.remove());
  });

  it("renders modal content when open", () => {
    render(
      <Modal open={true} title="Test Title" onClose={() => {}}>
        <p>Modal content</p>
      </Modal>
    );

    expect(screen.getByText("Test Title")).toBeInTheDocument();
    expect(screen.getByText("Modal content")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <Modal open={false} title="Test Title" onClose={() => {}}>
        <p>Modal content</p>
      </Modal>
    );

    expect(screen.queryByText("Test Title")).not.toBeInTheDocument();
  });

  it("allows focusing and typing into a field inside the modal", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(<TestModalWithForm onSave={onSave} />);

    const input = screen.getByTestId("modal-input");
    expect(input).toBeInTheDocument();

    await user.click(input);
    expect(input).toHaveFocus();

    // Use fireEvent.change because userEvent.type can have timing issues
    // with modal state updates during rapid re-renders
    fireEvent.change(input, { target: { value: "Hello World" } });
    expect(input).toHaveValue("Hello World");
  });

  it("allows clicking Save button inside modal", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(<TestModalWithForm onSave={onSave} />);

    const input = screen.getByTestId("modal-input");
    fireEvent.change(input, { target: { value: "Test Value" } });

    const saveButton = screen.getByRole("button", { name: "Save" });
    await user.click(saveButton);

    expect(onSave).toHaveBeenCalledWith("Test Value");
  });

  it("allows clicking Cancel button inside modal", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(<TestModalWithForm onSave={onSave} />);

    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    await user.click(cancelButton);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when clicking the backdrop", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <Modal open={true} title="Test" onClose={onClose}>
        <p>Content</p>
      </Modal>
    );

    const backdrop = document.querySelector(".modal-backdrop");
    expect(backdrop).toBeInTheDocument();

    await user.click(backdrop!);
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close when clicking inside the modal", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <Modal open={true} title="Test" onClose={onClose}>
        <p>Content</p>
      </Modal>
    );

    const modalContent = screen.getByText("Content");
    await user.click(modalContent);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes when pressing Escape", () => {
    const onClose = vi.fn();

    render(
      <Modal open={true} title="Test" onClose={onClose}>
        <p>Content</p>
      </Modal>
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("sets inert on #root when open", () => {
    render(
      <Modal open={true} title="Test" onClose={() => {}}>
        <p>Content</p>
      </Modal>
    );

    expect(rootEl).toHaveAttribute("inert");
  });

  it("removes inert from #root when closed", () => {
    const { rerender } = render(
      <Modal open={true} title="Test" onClose={() => {}}>
        <p>Content</p>
      </Modal>
    );

    expect(rootEl).toHaveAttribute("inert");

    rerender(
      <Modal open={false} title="Test" onClose={() => {}}>
        <p>Content</p>
      </Modal>
    );

    expect(rootEl).not.toHaveAttribute("inert");
  });

  it("renders via portal into document.body", () => {
    render(
      <Modal open={true} title="Test" onClose={() => {}}>
        <p>Content</p>
      </Modal>
    );

    const backdrop = document.querySelector(".modal-backdrop");
    expect(backdrop?.parentElement).toBe(document.body);
  });

  describe("Nested modals", () => {
    it("keeps #root inert when closing inner modal while outer is still open", async () => {
      const user = userEvent.setup();
      render(<NestedModalsTest />);

      expect(screen.getByText("Modal A")).toBeInTheDocument();
      expect(rootEl).toHaveAttribute("inert");

      const openBButton = screen.getByTestId("open-modal-b");
      await user.click(openBButton);

      expect(screen.getByText("Modal B")).toBeInTheDocument();
      expect(rootEl).toHaveAttribute("inert");

      const closeBButton = screen.getAllByRole("button", { name: "Close dialog" })[1];
      await user.click(closeBButton);

      expect(screen.queryByText("Modal B")).not.toBeInTheDocument();
      expect(screen.getByText("Modal A")).toBeInTheDocument();
      expect(rootEl).toHaveAttribute("inert");
    });

    it("allows interaction with outer modal after inner is closed", async () => {
      const user = userEvent.setup();
      render(<NestedModalsTest />);

      const openBButton = screen.getByTestId("open-modal-b");
      await user.click(openBButton);

      expect(screen.getByText("Modal B")).toBeInTheDocument();

      const closeBButton = screen.getAllByRole("button", { name: "Close dialog" })[1];
      await user.click(closeBButton);

      expect(screen.queryByText("Modal B")).not.toBeInTheDocument();

      const inputA = screen.getByTestId("input-a");
      await user.click(inputA);
      expect(inputA).toHaveFocus();
      await user.type(inputA, "test");
      expect(inputA).toHaveValue("test");
    });

    it("Escape closes only the topmost modal when multiple are open", async () => {
      const user = userEvent.setup();
      render(<NestedModalsTest />);

      const openBButton = screen.getByTestId("open-modal-b");
      await user.click(openBButton);

      expect(screen.getByText("Modal A")).toBeInTheDocument();
      expect(screen.getByText("Modal B")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "Escape" });

      expect(screen.queryByText("Modal B")).not.toBeInTheDocument();
      expect(screen.getByText("Modal A")).toBeInTheDocument();
      expect(rootEl).toHaveAttribute("inert");
    });

    it("removes inert only when all modals are closed", async () => {
      const user = userEvent.setup();
      render(<NestedModalsTest />);

      const openBButton = screen.getByTestId("open-modal-b");
      await user.click(openBButton);

      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.queryByText("Modal B")).not.toBeInTheDocument();
      expect(rootEl).toHaveAttribute("inert");

      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.queryByText("Modal A")).not.toBeInTheDocument();
      expect(rootEl).not.toHaveAttribute("inert");
    });
  });
});
