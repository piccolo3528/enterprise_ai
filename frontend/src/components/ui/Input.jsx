import { useId } from "react";

/**
 * A labelled text input. The label, hint and error are linked to the input for screen readers
 * (htmlFor / aria-describedby), and `aria-invalid` marks the field when there's an error.
 * `trailing` is an optional element shown inside the field on the right (e.g. a show/hide button).
 */
export default function Input({ label, hint, error, id, trailing, className = "", ...props }) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className={className}>
      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="relative mt-1.5">
        <input
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          className={`block w-full rounded-lg border-0 py-2 pl-3 text-sm text-slate-900 shadow-xs ring-1 ring-inset placeholder:text-slate-400 focus:ring-2 focus:ring-inset ${
            trailing ? "pr-10" : "pr-3"
          } ${error ? "ring-red-400 focus:ring-red-500" : "ring-slate-300 focus:ring-indigo-600"}`}
          {...props}
        />
        {trailing && <div className="absolute inset-y-0 right-0 flex items-center pr-2">{trailing}</div>}
      </div>
      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1.5 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
