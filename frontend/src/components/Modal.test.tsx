import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "./Modal";
import { useState } from "react";

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

describe("Modal", () => {
  let rootEl: HTMLDivElement;

  beforeEach(() => {
    rootEl = document.createElement("div");
    rootEl.id = "root";
    document.body.appendChild(rootEl);
  });

  afterEach(() => {
    cleanup();
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

    await user.type(input, "Hello World");
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
});
