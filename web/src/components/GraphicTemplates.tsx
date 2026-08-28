import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, previewUrl } from "@/lib/api";
import type { GraphicsCatalogue, GraphicsConfig, GraphicTemplate } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/Toasts";
import { Badge, Button, Panel, Skeleton, Tooltip } from "@/components/ui/primitives";

const CUSTOM = "custom";

export function GraphicTemplates() {
  const queryClient = useQueryClient();
  const { push } = useToast();

  const { data, isPending } = useQuery<GraphicsCatalogue>({
    queryKey: ["graphics"],
    queryFn: api.graphics,
  });

  /**
   * Bumped after every save or upload so the preview <img> URLs change and the
   * browser refetches them. Previews are rendered server-side and cached on
   * disk, so without this the picker shows stale artwork.
   */
  const [version, setVersion] = React.useState(() => Date.now());
  const bump = () => setVersion(Date.now());

  const save = useMutation({
    mutationFn: (patch: Partial<GraphicsConfig>) =>
      api.saveGraphics({ ...data!.graphics, ...patch }),
    onSuccess: (result) => {
      queryClient.setQueryData(["graphics"], (old: GraphicsCatalogue | undefined) =>
        old ? { ...old, graphics: result.graphics } : old,
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      bump();
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: "background" | "logo"; file: File }) =>
      api.uploadArtwork(kind, file),
    onSuccess: (result, { kind }) => {
      queryClient.setQueryData(["graphics"], (old: GraphicsCatalogue | undefined) =>
        old ? { ...old, graphics: result.graphics } : old,
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      bump();
      push(`${kind === "logo" ? "Logo" : "Background"} uploaded.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (kind: "background" | "logo") => api.deleteArtwork(kind),
    onSuccess: (result) => {
      queryClient.setQueryData(["graphics"], (old: GraphicsCatalogue | undefined) =>
        old ? { ...old, graphics: result.graphics } : old,
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      bump();
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !data) return <Skeleton className="h-96" />;

  const { graphics, templates } = data;
  const busy = save.isPending || upload.isPending || remove.isPending;

  return (
    <div className="space-y-6">
      <Panel
        title="Result graphic template"
        description="Applies to the match graphic and the overall standings PNG, every time you save a match."
        actions={busy ? <Badge tone="neutral">Saving…</Badge> : null}
      >
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {templates.map((template) => (
            <TemplateCard
              key={template.key}
              template={template}
              selected={graphics.template === template.key}
              version={version}
              disabled={busy}
              onSelect={() => save.mutate({ template: template.key })}
            />
          ))}
        </ul>
      </Panel>

      <Panel
        title="Your own graphics"
        description="Upload a background and a logo. They work with any template — pick “Custom” for the plainest table so your artwork does the talking."
      >
        <div className="grid gap-6 lg:grid-cols-2">
          <ArtworkSlot
            kind="background"
            label="Background image"
            hint="1920×1080 works best. Anything else is scaled to fill and centre-cropped. The app dims it automatically so the standings stay readable."
            current={graphics.background}
            version={version}
            disabled={busy}
            onUpload={(file) => upload.mutate({ kind: "background", file })}
            onRemove={() => remove.mutate("background")}
          />
          <ArtworkSlot
            kind="logo"
            label="Logo"
            hint="PNG with transparency looks best. Placed in a corner at up to 150×150."
            current={graphics.logo}
            version={version}
            disabled={busy}
            onUpload={(file) => upload.mutate({ kind: "logo", file })}
            onRemove={() => remove.mutate("logo")}
          />
        </div>

        <div className="mt-6 grid gap-4 border-t border-line pt-6 sm:grid-cols-2 lg:grid-cols-4">
          <ColourField
            label="Accent colour"
            value={graphics.accent}
            placeholder="template default"
            disabled={busy}
            onCommit={(accent) => save.mutate({ accent })}
          />
          <ColourField
            label="Team name colour"
            value={graphics.text}
            placeholder="template default"
            disabled={busy}
            onCommit={(text) => save.mutate({ text })}
          />

          <div>
            <label className="label" htmlFor="logo-position">
              Logo corner
            </label>
            <select
              id="logo-position"
              className="field"
              value={graphics.logoPosition}
              disabled={busy || !graphics.logo}
              onChange={(event) => save.mutate({ logoPosition: event.target.value })}
            >
              {data.logoPositions.map((position) => (
                <option key={position} value={position}>
                  {position.replace("-", " ")}
                </option>
              ))}
            </select>
            <label className="mt-2 flex items-center gap-2 text-xs text-muted">
              <input
                type="checkbox"
                className="size-4 accent-[hsl(var(--bronze))]"
                checked={graphics.showLogo}
                disabled={busy || !graphics.logo}
                onChange={(event) => save.mutate({ showLogo: event.target.checked })}
              />
              Show the logo
            </label>
          </div>

          <div>
            <label className="label" htmlFor="layout-override">
              Table layout
            </label>
            <select
              id="layout-override"
              className="field"
              value={graphics.layout}
              disabled={busy}
              onChange={(event) => save.mutate({ layout: event.target.value })}
            >
              <option value="">Template default</option>
              <option value="1">One column</option>
              <option value="2">Two columns</option>
            </select>
            <p className="mt-2 text-xs text-muted">
              One column switches itself to two when a lobby is too big to stay legible.
            </p>
          </div>
        </div>

        {graphics.background && (
          <div className="mt-6 border-t border-line pt-6">
            <label className="label" htmlFor="scrim">
              Background dimming — {graphics.scrim ?? "auto"}
            </label>
            <input
              id="scrim"
              type="range"
              min={0}
              max={255}
              step={5}
              className="w-full max-w-md accent-[hsl(var(--bronze))]"
              value={graphics.scrim ?? 130}
              disabled={busy}
              onChange={(event) => save.mutate({ scrim: Number(event.target.value) })}
            />
            <p className="mt-1 text-xs text-muted">
              Left keeps your artwork bright; right darkens it behind the table.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}

function TemplateCard({
  template,
  selected,
  version,
  disabled,
  onSelect,
}: {
  template: GraphicTemplate;
  selected: boolean;
  version: number;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        disabled={disabled}
        aria-pressed={selected}
        className={cn(
          "group w-full overflow-hidden rounded-panel border text-left transition",
          "disabled:cursor-not-allowed disabled:opacity-60",
          selected
            ? "border-bronze ring-2 ring-bronze/50"
            : "border-line hover:border-bronze/60",
        )}
      >
        {/*
          Loaded eagerly on purpose. These previews are the entire point of the
          panel, they are small and server-cached, and lazy loading makes them
          depend on paint-driven visibility heuristics — when those do not fire
          the picker renders as eleven empty grey boxes.
        */}
        <img
          src={previewUrl(template.key, version)}
          alt={`${template.name} preview`}
          decoding="async"
          className="aspect-video w-full bg-raised object-cover"
        />
        <div className="space-y-1.5 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-sand">{template.name}</span>
            {selected ? (
              <Badge tone="bronze">In use</Badge>
            ) : (
              <span className="text-[11px] text-muted">
                {template.key === CUSTOM ? "your artwork" : `${template.columns} column`}
              </span>
            )}
          </div>
          <p className="line-clamp-2 text-xs leading-relaxed text-muted">{template.blurb}</p>
          <div className="flex gap-1 pt-0.5" aria-hidden>
            {template.swatch.map((colour, index) => (
              <span
                key={index}
                className="h-2 flex-1 rounded-full border border-black/20"
                style={{ background: colour }}
              />
            ))}
          </div>
        </div>
      </button>
    </li>
  );
}

function ArtworkSlot({
  kind,
  label,
  hint,
  current,
  version,
  disabled,
  onUpload,
  onRemove,
}: {
  kind: "background" | "logo";
  label: string;
  hint: string;
  current: string;
  version: number;
  disabled: boolean;
  onUpload: (file: File) => void;
  onRemove: () => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);

  // The file is served back through the preview render rather than directly,
  // so the thumbnail uses the same cache-busting version.
  const thumbnail = current ? previewUrl(CUSTOM, `${version}-${kind}`) : "";

  return (
    <div>
      <p className="label">{label}</p>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file && !disabled) onUpload(file);
        }}
        className={cn(
          "rounded-panel border-2 border-dashed p-4 transition",
          dragging ? "border-bronze bg-bronze/5" : "border-line",
          disabled && "opacity-60",
        )}
      >
        {current ? (
          <div className="space-y-3">
            <img
              src={thumbnail}
              alt={`${label} in place`}
              className="aspect-video w-full rounded-lg border border-line object-cover"
            />
            <div className="flex items-center justify-between gap-2">
              <Tooltip label="Stored with this event, not shared between events.">
                <span className="truncate text-xs text-muted">{current}</span>
              </Tooltip>
              <div className="flex gap-2">
                <Button size="sm" disabled={disabled} onClick={() => inputRef.current?.click()}>
                  Replace
                </Button>
                <Button size="sm" variant="danger" disabled={disabled} onClick={onRemove}>
                  Remove
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-6 text-center">
            <p className="text-sm text-sand">Drop an image, or</p>
            <Button
              size="sm"
              className="mt-3"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
            >
              Choose a file
            </Button>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
        />
      </div>
      <p className="mt-2 text-xs text-muted">{hint}</p>
    </div>
  );
}

function ColourField({
  label,
  value,
  placeholder,
  disabled,
  onCommit,
}: {
  label: string;
  value: string;
  placeholder: string;
  disabled: boolean;
  onCommit: (value: string) => void;
}) {
  const [draft, setDraft] = React.useState(value);
  React.useEffect(() => setDraft(value), [value]);

  const id = React.useId();
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <div className="flex gap-2">
        {/*
          Committing on `change` rather than `input` means dragging through the
          colour wheel fires one save at the end, not one per pixel — each save
          re-renders every export on the server.
        */}
        <input
          type="color"
          aria-label={`${label} picker`}
          className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-line bg-raised p-1"
          value={draft || "#e8be52"}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => draft !== value && onCommit(draft)}
        />
        <input
          id={id}
          className="field min-w-0 font-mono text-xs"
          placeholder={placeholder}
          value={draft}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => draft !== value && onCommit(draft)}
        />
      </div>
      {value && (
        <button
          type="button"
          className="mt-1 text-xs text-muted underline hover:text-sand"
          disabled={disabled}
          onClick={() => onCommit("")}
        >
          Reset to template
        </button>
      )}
    </div>
  );
}
