import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { Toast } from "./components/Toast";
import { AuthError } from "./api/client";
import "./styles.css";

function notifyError(error: unknown) {
  if (error instanceof AuthError) return;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  window.dispatchEvent(new CustomEvent("app:toast", { detail: message }));
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: notifyError,
  }),
  mutationCache: new MutationCache({
    onError: notifyError,
  }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toast />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
