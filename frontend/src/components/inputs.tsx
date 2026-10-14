import { ChangeEvent, InputHTMLAttributes, forwardRef, useId, useState } from "react";
import { parseDecimalInput } from "../lib/format";

type MoneyInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  currency?: "BRL" | "USD";
  error?: string;
  label?: string;
  onValueChange?: (value: string) => void;
};

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(
  function MoneyInput({ currency = "BRL", error, label, className, onValueChange, onChange, ...props }, ref) {
    const id = useId();
    const errorId = `${id}-error`;
    const prefix = currency === "BRL" ? "R$" : "$";

    function handleChange(event: ChangeEvent<HTMLInputElement>) {
      onChange?.(event);
      if (onValueChange) {
        const parsed = parseDecimalInput(event.target.value);
        if (parsed !== null) {
          onValueChange(parsed);
        }
      }
    }

    return (
      <div className={`input-group ${className || ""}`}>
        {label ? <label htmlFor={id}>{label}</label> : null}
        <div className="input-affix">
          <span className="input-prefix">{prefix}</span>
          <input
            ref={ref}
            id={id}
            inputMode="decimal"
            autoComplete="off"
            aria-invalid={error ? "true" : undefined}
            aria-describedby={error ? errorId : undefined}
            onChange={handleChange}
            {...props}
          />
        </div>
        {error ? <span id={errorId} className="input-error">{error}</span> : null}
      </div>
    );
  }
);

type PercentInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  error?: string;
  label?: string;
  min?: number;
  max?: number;
  onValueChange?: (value: string) => void;
};

export const PercentInput = forwardRef<HTMLInputElement, PercentInputProps>(
  function PercentInput({ error, label, min, max, className, onValueChange, onChange, ...props }, ref) {
    const id = useId();
    const errorId = `${id}-error`;
    const [validationError, setValidationError] = useState<string | null>(null);

    function handleChange(event: ChangeEvent<HTMLInputElement>) {
      onChange?.(event);
      const parsed = parseDecimalInput(event.target.value);
      if (parsed !== null) {
        const num = parseFloat(parsed);
        if (min !== undefined && num < min) {
          setValidationError(`Min: ${min}%`);
        } else if (max !== undefined && num > max) {
          setValidationError(`Max: ${max}%`);
        } else {
          setValidationError(null);
        }
        onValueChange?.(parsed);
      }
    }

    const displayError = error || validationError;

    return (
      <div className={`input-group ${className || ""}`}>
        {label ? <label htmlFor={id}>{label}</label> : null}
        <div className="input-affix">
          <input
            ref={ref}
            id={id}
            inputMode="decimal"
            autoComplete="off"
            aria-invalid={displayError ? "true" : undefined}
            aria-describedby={displayError ? errorId : undefined}
            onChange={handleChange}
            {...props}
          />
          <span className="input-suffix">%</span>
        </div>
        {displayError ? <span id={errorId} className="input-error">{displayError}</span> : null}
      </div>
    );
  }
);

type IntInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  error?: string;
  label?: string;
  min?: number;
  max?: number;
  onValueChange?: (value: string) => void;
};

export const IntInput = forwardRef<HTMLInputElement, IntInputProps>(
  function IntInput({ error, label, min, max, className, onValueChange, onChange, ...props }, ref) {
    const id = useId();
    const errorId = `${id}-error`;
    const [validationError, setValidationError] = useState<string | null>(null);

    function handleChange(event: ChangeEvent<HTMLInputElement>) {
      onChange?.(event);
      const value = event.target.value.replace(/\D/g, "");
      const num = parseInt(value, 10);
      if (!isNaN(num)) {
        if (min !== undefined && num < min) {
          setValidationError(`Min: ${min}`);
        } else if (max !== undefined && num > max) {
          setValidationError(`Max: ${max}`);
        } else {
          setValidationError(null);
        }
        onValueChange?.(String(num));
      }
    }

    const displayError = error || validationError;

    return (
      <div className={`input-group ${className || ""}`}>
        {label ? <label htmlFor={id}>{label}</label> : null}
        <input
          ref={ref}
          id={id}
          inputMode="numeric"
          autoComplete="off"
          aria-invalid={displayError ? "true" : undefined}
          aria-describedby={displayError ? errorId : undefined}
          onChange={handleChange}
          {...props}
        />
        {displayError ? <span id={errorId} className="input-error">{displayError}</span> : null}
      </div>
    );
  }
);

export function showToast(message: string) {
  window.dispatchEvent(new CustomEvent("app:toast", { detail: message }));
}
