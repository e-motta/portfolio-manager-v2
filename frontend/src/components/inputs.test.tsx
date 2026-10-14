import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MoneyInput } from "./inputs";

describe("MoneyInput", () => {
  it("calls onValueChange with parsed value for valid input", () => {
    const onChange = vi.fn();
    render(<MoneyInput label="Amount" onValueChange={onChange} />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "1.234,56" } });
    expect(onChange).toHaveBeenCalledWith("1234.56", null);
  });

  it("calls onValueChange with empty string and error for invalid input", () => {
    const onChange = vi.fn();
    render(<MoneyInput label="Amount" onValueChange={onChange} />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "abc" } });
    expect(onChange).toHaveBeenCalledWith("", "Invalid amount");
  });

  it("displays error message for invalid input", () => {
    render(<MoneyInput label="Amount" />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "not a number" } });
    expect(screen.getByText("Invalid amount")).toBeInTheDocument();
  });

  it("clears error when input becomes valid", () => {
    render(<MoneyInput label="Amount" />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "abc" } });
    expect(screen.getByText("Invalid amount")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "123,45" } });
    expect(screen.queryByText("Invalid amount")).not.toBeInTheDocument();
  });

  it("sets aria-invalid when there is an error", () => {
    render(<MoneyInput label="Amount" />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "xyz" } });
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("clears error and value for empty input", () => {
    const onChange = vi.fn();
    render(<MoneyInput label="Amount" onValueChange={onChange} />);
    const input = screen.getByLabelText("Amount");
    fireEvent.change(input, { target: { value: "abc" } });
    expect(onChange).toHaveBeenLastCalledWith("", "Invalid amount");
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("", null);
  });

  it("shows external error prop", () => {
    render(<MoneyInput label="Amount" error="Required field" />);
    expect(screen.getByText("Required field")).toBeInTheDocument();
  });
});
