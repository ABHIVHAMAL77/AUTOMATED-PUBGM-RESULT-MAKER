import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { ToastProvider } from "./components/Toasts";
import { TooltipProvider } from "./components/ui/primitives";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Auth failures must surface immediately rather than being retried into
      // a multi-second hang on the login screen.
      retry: (failureCount, error) =>
        !(error instanceof Error && error.name === "ApiError") && failureCount < 2,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.querySelector("#root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
