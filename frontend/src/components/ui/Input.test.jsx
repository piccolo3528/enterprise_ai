import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Input from "./Input";

describe("Input", () => {
  it("is reachable by its label", () => {
    render(<Input label="Email" type="email" />);
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
  });

  it("marks the field invalid and links the error message", () => {
    render(<Input label="Email" error="Enter a valid email address" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter a valid email address");
  });

  it("shows the hint only when there is no error", () => {
    const { rerender } = render(<Input label="Name" hint="As shown on your profile" />);
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("As shown on your profile");
    rerender(<Input label="Name" hint="As shown on your profile" error="Required" />);
    expect(screen.queryByText("As shown on your profile")).not.toBeInTheDocument();
  });
});
