import { BrainCircuit } from "lucide-react";

/** Centred card used by the sign-in and sign-up pages. */
export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-12">
      <div className="mb-8 flex items-center gap-2.5">
        <span className="flex size-10 items-center justify-center rounded-xl bg-indigo-600">
          <BrainCircuit aria-hidden="true" className="size-6 text-white" />
        </span>
        <span className="text-lg font-semibold text-slate-900">Knowledge Intelligence</span>
      </div>
      <main className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </main>
      {footer && <p className="mt-6 text-sm text-slate-600">{footer}</p>}
    </div>
  );
}
