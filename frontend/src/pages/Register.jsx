import { useState } from "react";
import { Link, useLocation } from "react-router";

import { fieldErrors } from "../api/client";
import AuthLayout from "../components/layout/AuthLayout";
import Button from "../components/ui/Button";
import ErrorBanner from "../components/ui/ErrorBanner";
import Input from "../components/ui/Input";
import PasswordInput from "../components/ui/PasswordInput";
import { useAuth } from "../context/AuthContext";

export const PASSWORD_MIN = 8; // must match the backend (app/schemas/auth.py)

export default function Register() {
  const { signUp } = useAuth();
  const location = useLocation();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signUp({ email, password, fullName });
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  const errors = fieldErrors(error);

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Your documents and conversations are visible only to you."
      footer={
        <>
          Already have an account?{" "}
          <Link
            to="/login"
            state={location.state}
            className="font-medium text-indigo-600 hover:text-indigo-500"
          >
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && !error.details && (
          <ErrorBanner title="Couldn't create your account" error={error} />
        )}
        <Input
          label="Full name"
          autoComplete="name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          error={errors.full_name}
        />
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
          autoComplete="new-password"
          required
          minLength={PASSWORD_MIN}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint={`At least ${PASSWORD_MIN} characters. A short phrase is easy to remember and strong.`}
          error={errors.password}
        />
        <Button type="submit" loading={submitting} className="w-full">
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
