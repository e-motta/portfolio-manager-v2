import { useRef, useState } from "react";

type FileDropProps = {
  accept?: string;
  label: string;
  hint?: string;
  onFile: (file: File) => void;
};

export function FileDrop({ accept, label, hint, onFile }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  function take(file: File | undefined) {
    if (!file) return;
    setName(file.name);
    onFile(file);
  }

  return (
    <div className="file-drop">
      <span className="file-drop__label">{label}</span>
      <button
        type="button"
        className={`file-drop__zone${over ? " is-over" : ""}${name ? " has-file" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          take(event.dataTransfer.files[0]);
        }}
      >
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
          <path d="M12 16V4M8 8l4-4 4 4M5 16v3h14v-3" fill="none" stroke="currentColor" strokeWidth="1.7" />
        </svg>
        <span>
          {name ? <strong>{name}</strong> : "Drop a CSV here or browse"}
        </span>
        {hint ? <small>{hint}</small> : null}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(event) => {
          take(event.target.files?.[0]);
          event.currentTarget.value = "";
        }}
      />
    </div>
  );
}
