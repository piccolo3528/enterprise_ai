import Spinner from "./Spinner";

const VARIANTS = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:outline-indigo-600",
  secondary:
    "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 focus-visible:outline-indigo-600",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-indigo-600",
  danger: "bg-red-600 text-white hover:bg-red-500 focus-visible:outline-red-600",
};

const SIZES = {
  sm: "gap-1.5 px-2.5 py-1.5 text-sm",
  md: "gap-2 px-3.5 py-2 text-sm",
};

/**
 * `loading` disables the button and shows a spinner, so a slow request can't be sent twice.
 * `icon` is a lucide icon component shown before the label.
 */
export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon: Icon,
  type = "button",
  disabled,
  className = "",
  children,
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center rounded-lg font-medium shadow-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <Spinner label="Working" className="size-4 text-current" />
      ) : (
        Icon && <Icon aria-hidden="true" className="size-4" />
      )}
      {children}
    </button>
  );
}
