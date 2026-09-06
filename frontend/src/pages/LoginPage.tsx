import { useQuery } from "@tanstack/react-query";
import { Navigate, useSearchParams } from "react-router-dom";
import { getJson } from "../api/client";

type AuthConfig = {
  google_configured: boolean;
  authenticated: boolean;
  error: string | null;
};

export function LoginPage() {
  const [params] = useSearchParams();
  const query = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => getJson<AuthConfig>("/api/auth/config"),
  });

  if (query.data?.authenticated) {
    return <Navigate to="/" replace />;
  }

  const error = params.get("error") || query.data?.error;

  return (
    <div className="login">
      <main className="login-card">
        <div className="brand">
          <strong>Portfolio</strong>
          <span>Manager</span>
        </div>
        <h1>Sign in to continue</h1>
        <p>Use your Google account to open your portfolio and finance books.</p>
        {error ? <p className="login-error" role="alert">{error}</p> : null}
        {query.data && !query.data.google_configured ? (
          <p className="login-error">
            Google login is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.
          </p>
        ) : (
          <a className="btn" href="/auth/google">
            Continue with Google
          </a>
        )}
      </main>
    </div>
  );
}
