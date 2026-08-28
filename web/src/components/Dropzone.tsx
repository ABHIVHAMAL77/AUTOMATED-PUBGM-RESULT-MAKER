import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/primitives";

const ACCEPTED = [".png", ".jpg", ".jpeg", ".bmp", ".webp"];

export interface Shot {
  file: File;
  url: string;
}

/**
 * Drag-and-drop screenshot picker with thumbnails.
 *
 * The old UI was a bare `<input type=file multiple>` with no feedback at all:
 * you could not tell which files you had selected, in what order, or drop one
 * you picked by mistake without starting over.
 */
export function Dropzone({
  shots,
  onChange,
  disabled,
  label,
  hint,
}: {
  shots: Shot[];
  onChange: (shots: Shot[]) => void;
  disabled?: boolean;
  label: string;
  hint: string;
}) {
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const add = React.useCallback(
    (files: FileList | null) => {
      if (!files?.length) return;
      const accepted = [...files].filter((file) =>
        ACCEPTED.some((extension) => file.name.toLowerCase().endsWith(extension)),
      );
      onChange([...shots, ...accepted.map((file) => ({ file, url: URL.createObjectURL(file) }))]);
    },
    [onChange, shots],
  );

  // Object URLs are revoked when the component unmounts; leaving them alive
  // pins every screenshot's bytes in memory for the life of the tab.
  React.useEffect(
    () => () => {
      for (const shot of shots) URL.revokeObjectURL(shot.url);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function remove(index: number) {
    URL.revokeObjectURL(shots[index].url);
    onChange(shots.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) add(event.dataTransfer.files);
        }}
        className={cn(
          "rounded-panel border-2 border-dashed px-4 py-8 text-center transition",
          dragging ? "border-bronze bg-bronze/5" : "border-line",
          disabled && "opacity-50",
        )}
      >
        <p className="text-sm font-medium text-sand">{label}</p>
        <p className="mx-auto mt-1 max-w-md text-xs text-muted">{hint}</p>
        <Button
          type="button"
          className="mt-4"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Choose screenshots
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED.join(",")}
          className="sr-only"
          onChange={(event) => {
            add(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {shots.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {shots.map((shot, index) => (
            <li key={shot.url} className="group relative overflow-hidden rounded-lg border border-line">
              <img
                src={shot.url}
                alt={shot.file.name}
                className="aspect-video w-full object-cover"
                loading="lazy"
              />
              <div className="flex items-center justify-between gap-2 bg-raised px-2 py-1.5">
                <span className="truncate text-[11px] text-muted" title={shot.file.name}>
                  {shot.file.name}
                </span>
                <button
                  type="button"
                  onClick={() => remove(index)}
                  disabled={disabled}
                  aria-label={`Remove ${shot.file.name}`}
                  className="shrink-0 rounded px-1 text-muted transition hover:text-danger disabled:opacity-40"
                >
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
