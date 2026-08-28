import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/primitives";

const BRAND_LOGO = "/ec-logo.png";

type Mode = "login" | "register";

export default function AuthPage() {
  const [mode, setMode] = React.useState<Mode>("login");
  const [form, setForm] = React.useState({ email: "", password: "", name: "" });
  // Field-level errors instead of one global string — the old app could only
  // tell you "something went wrong" somewhere on the page.
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const queryClient = useQueryClient();

  const submit = useMutation({
    mutationFn: async () => {
      if (mode === "login") return api.login(form.email, form.password);
      return api.register(form.email, form.password, form.name);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
    onError: (error: Error) => setErrors({ form: error.message }),
  });

  function validate() {
    const next: Record<string, string> = {};
    if (!form.email.trim()) next.email = "Enter your email address.";
    else if (!form.email.includes("@")) next.email = "That does not look like an email address.";
    if (!form.password) next.password = "Enter your password.";
    else if (mode === "register" && form.password.length < 6)
      next.password = "Use at least 6 characters.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (validate()) submit.mutate();
  }

  const field = (name: keyof typeof form) => ({
    value: form[name],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [name]: event.target.value }));
      setErrors((current) => ({ ...current, [name]: "", form: "" }));
    },
    "aria-invalid": Boolean(errors[name]) || undefined,
    "aria-describedby": errors[name] ? `${name}-error` : undefined,
    className: cn("field", errors[name] && "border-danger focus:border-danger"),
  });

  return (
    <div className="mx-auto grid min-h-full max-w-6xl items-center gap-10 px-4 py-10 lg:grid-cols-2 lg:gap-16">
      <div>
        <img
          src={BRAND_LOGO}
          alt="ESPORTS COUNTY logo"
          className="mb-6 size-28 object-contain drop-shadow-[0_0_28px_rgba(199,124,58,0.35)] sm:size-32"
        />
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-bronze">
          licensed tournament tool
        </p>
        <h1 className="mt-3 text-3xl font-bold leading-tight sm:text-4xl">
          ESPORTS COUNTY
          <span className="block text-bronze-bright">PUBGM Result Maker</span>
        </h1>
        <p className="mt-4 max-w-md text-muted">
          Read match results straight off your screenshots, check them once, and get standings,
          player stats, sheets and broadcast graphics out the other side.
        </p>
        <ul className="mt-6 space-y-2 text-sm text-muted">
          {[
            "Screenshot OCR with a confidence score on every row",
            "Observer API mode for live matches",
            "Excel sheet and PNG graphics on every save",
          ].map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden className="text-bronze">
                ◆
              </span>
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="panel p-6 sm:p-8">
        <div role="tablist" aria-label="Account" className="mb-6 flex gap-1 rounded-lg bg-raised p-1">
          {(["login", "register"] as Mode[]).map((value) => (
            <button
              key={value}
              role="tab"
              type="button"
              aria-selected={mode === value}
              onClick={() => {
                setMode(value);
                setErrors({});
              }}
              className={cn(
                "flex-1 rounded-md px-3 py-2 text-sm capitalize transition",
                mode === value ? "bg-bronze font-semibold text-ink" : "text-muted hover:text-sand",
              )}
            >
              {value === "login" ? "Log in" : "Create account"}
            </button>
          ))}
        </div>

        <form onSubmit={onSubmit} noValidate className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="label" htmlFor="name">
                Your name
              </label>
              <input id="name" autoComplete="name" {...field("name")} />
            </div>
          )}

          <div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input id="email" type="email" autoComplete="email" {...field("email")} />
            {errors.email && (
              <p id="email-error" className="mt-1 text-xs text-danger">
                {errors.email}
              </p>
            )}
          </div>

          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              {...field("password")}
            />
            {errors.password && (
              <p id="password-error" className="mt-1 text-xs text-danger">
                {errors.password}
              </p>
            )}
          </div>

          {errors.form && (
            <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
              {errors.form}
            </p>
          )}

          <Button type="submit" variant="primary" loading={submit.isPending} className="w-full">
            {mode === "login" ? "Log in" : "Create account"}
          </Button>

          {mode === "register" && (
            <p className="text-xs text-muted">
              Registration is limited to purchased email addresses. If yours is rejected, contact
              ESPORTS COUNTY to be added to the allowlist.
            </p>
          )}
        </form>
      </div>
    </div>
  );
}

