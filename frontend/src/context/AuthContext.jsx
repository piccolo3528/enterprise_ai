import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import * as authApi from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";

const AuthContext = createContext(null);

/**
 * Who is signed in, shared with the whole app.
 *
 * status: "loading"        asking the backend (GET /api/auth/me) on first load
 *         "authenticated"  `user` is set
 *         "anonymous"      not signed in (or the session expired)
 *         "error"          couldn't ask: the backend is unreachable; `error` says why
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null); // shown once on the sign-in page

  const checkSession = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setUser(await authApi.getMe());
      setStatus("authenticated");
    } catch (err) {
      setUser(null);
      if (err.code === "unauthorized") {
        setStatus("anonymous");
      } else {
        // Don't pretend the user is signed out when we simply couldn't ask.
        setError(err);
        setStatus("error");
      }
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  useEffect(() => {
    // Any API call that finds the session expired sends the user back to sign in, with the
    // server's reason ("expired", or "signed out because your password changed", M16).
    setUnauthorizedHandler((err) => {
      setUser(null);
      setStatus("anonymous");
      setNotice(err?.message || "Your session has expired. Please sign in again.");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = useCallback(async (credentials) => {
    const signedIn = await authApi.login(credentials);
    setUser(signedIn);
    setStatus("authenticated");
    setNotice(null);
    return signedIn;
  }, []);

  const signUp = useCallback(async (details) => {
    const created = await authApi.register(details);
    setUser(created);
    setStatus("authenticated");
    setNotice(null);
    return created;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      // Even if the request fails, forget the user locally; the cookie expires on its own.
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  /** Ends every session (password-change style); back to sign-in with a notice. */
  const signOutEverywhere = useCallback(async () => {
    await authApi.logoutEverywhere();
    setUser(null);
    setStatus("anonymous");
    setNotice("You've been signed out on every device.");
  }, []);

  // `updateUser`: the Settings page saved the profile or preferences (the server's copy).
  const value = useMemo(
    () => ({
      user,
      status,
      error,
      notice,
      checkSession,
      signIn,
      signUp,
      signOut,
      signOutEverywhere,
      updateUser: setUser,
    }),
    [user, status, error, notice, checkSession, signIn, signUp, signOut, signOutEverywhere],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
