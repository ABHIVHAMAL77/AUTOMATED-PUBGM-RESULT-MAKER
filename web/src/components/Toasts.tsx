import * as React from "react";
import { cn } from "@/lib/utils";

type Tone = "info" | "success" | "error";
interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

const ToastContext = React.createContext<{
  push: (message: string, tone?: Tone) => void;
}>({ push: () => {} });

export const useToast = () => React.useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const push = React.useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, tone, message }]);
    window.setTimeout(
      () => setToasts((current) => current.filter((t) => t.id !== id)),
      tone === "error" ? 8000 : 4000,
    );
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      {/*
        aria-live so a screen reader announces the result of an action. The
        old app wrote status into a plain div, which announced nothing.
      */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto animate-fade-in rounded-lg border px-4 py-3 text-sm shadow-xl backdrop-blur",
              toast.tone === "error" && "border-danger/50 bg-panel text-danger",
              toast.tone === "success" && "border-ok/50 bg-panel text-ok",
              toast.tone === "info" && "border-line bg-panel text-sand",
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
