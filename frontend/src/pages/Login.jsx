import { useState } from "react";
import { Link, useLocation } from "react-router";

import { fieldErrors } from "../api/client";
import AuthLayout from "../components/layout/AuthLayout";
import Button from "../components/ui/Button";
import ErrorBanner from "../components/ui/ErrorBanner";
import Input from "../components/ui/Input";
import PasswordInput from "../components/ui/PasswordInput";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { signIn, notice } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signIn({ email, password });
      // No navigate() here: once signed in, the route guard sends the user on.
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  const errors = fieldErrors(error);

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Ask questions about your documents."
      footer={
        <>
          New here?{" "}
          <Link
            to="/register"
            state={location.state}
            className="font-medium text-indigo-600 hover:text-indigo-500"
          >
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {notice && !error && (
          <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {notice}
          </p>
        )}
        {error && !error.details && <ErrorBanner title="Couldn't sign you in" error={error} />}
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <Button type="submit" loading={submitting} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
