import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe, login, logout, register } from "./api/auth";
import { ApiError } from "./api/client";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));
vi.mock("./api/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}));

const notSignedIn = () =>
  new ApiError({ status: 401, code: "unauthorized", message: "Please sign in to continue." });

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockRejectedValue(notSignedIn());
});

describe("signing in", () => {
  it("sends anonymous visitors to the sign-in page", async () => {
    renderApp("/status");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "System status" })).not.toBeInTheDocument();
  });

  it("signs in and returns to the page that was asked for", async () => {
    login.mockResolvedValue(TEST_USER);
    renderApp("/status");
    await userEvent.type(await screen.findByLabelText("Email"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(login).toHaveBeenCalledWith({ email: "ana@example.com", password: "a-long-passphrase" });
  });

  it("shows the server's message when the password is wrong", async () => {
    login.mockRejectedValue(
      new ApiError({ status: 401, code: "unauthorized", message: "Incorrect email or password." }),
    );
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("lets the user reveal the password they typed", async () => {
    renderApp("/login");
    const field = await screen.findByLabelText("Password");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
  });

  it("sends an already signed-in user away from the sign-in page", async () => {
    getMe.mockResolvedValue(TEST_USER);
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
  });

  it("explains when the server can't be reached instead of showing the sign-in page", async () => {
    getMe.mockRejectedValue(
      new ApiError({ status: 502, code: "backend_unreachable", message: "Can't reach the backend." }),
    );
    renderApp("/status");
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the backend.");
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });
});

describe("creating an account", () => {
  async function fillRegistration() {
    await userEvent.type(await screen.findByLabelText("Full name"), "Ana Silva");
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
  }

  it("registers and lands in the app", async () => {
    register.mockResolvedValue(TEST_USER);
    renderApp("/register");
    await fillRegistration();
    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(register).toHaveBeenCalledWith({
      email: "ana@example.com",
      password: "a-long-passphrase",
      fullName: "Ana Silva",
    });
  });

  it("explains a duplicate email", async () => {
    register.mockRejectedValue(
      new ApiError({
        status: 409,
        code: "conflict",
        message: "An account with this email already exists.",
      }),
    );
    renderApp("/register");
    await fillRegistration();
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });

  it("shows field errors from the server next to the field", async () => {
    register.mockRejectedValue(
      new ApiError({
        status: 422,
        code: "validation_error",
        message: "Some fields are missing or invalid.",
        details: [{ field: "body.password", message: "String should have at least 8 characters" }],
      }),
    );
    renderApp("/register");
    await fillRegistration();
    const password = screen.getByLabelText("Password");
    expect(await screen.findByText("String should have at least 8 characters")).toBeInTheDocument();
    expect(password).toHaveAttribute("aria-invalid", "true");
  });
});

describe("signing out", () => {
  it("signs out and returns to the sign-in page", async () => {
    getMe.mockResolvedValue(TEST_USER);
    logout.mockResolvedValue();
    renderApp("/status");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
  });
});
