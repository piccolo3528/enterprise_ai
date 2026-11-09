import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "../../context/AuthContext";
import ErrorBanner from "../ui/ErrorBanner";
import Spinner from "../ui/Spinner";

function FullPage({ children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">{children}</div>
  );
}

function SessionCheck() {
  const { status, error, checkSession } = useAuth();
  if (status === "loading") {
    return (
      <FullPage>
        <Spinner label="Checking your session" className="size-8" />
      </FullPage>
    );
  }
  if (status === "error") {
    return (
      <FullPage>
        <div className="w-full max-w-md">
          <ErrorBanner title="Couldn't reach the server" error={error} onRetry={checkSession} />
        </div>
      </FullPage>
    );
  }
  return null;
}

/** Pages for signed-in users. Anyone else goes to /login, then comes back here afterwards. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading" || status === "error") return <SessionCheck />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/**
 * Sign-in and sign-up pages. Once the user is signed in (already, or by submitting the form),
 * this sends them on: back to the page they originally asked for, or to the home page.
 */
export function PublicOnlyRoute() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading" || status === "error") return <SessionCheck />;
  if (status === "authenticated") return <Navigate to={location.state?.from ?? "/"} replace />;
  return <Outlet />;
}
