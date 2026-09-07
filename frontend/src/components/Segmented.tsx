type Option<T extends string> = { value: T; label: string };

type SegmentedProps<T extends string> = {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  label?: string;
};

export function Segmented<T extends string>({ value, options, onChange, label }: SegmentedProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={value === option.value ? "is-active" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
