import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * An accessible dialog, used instead of window.confirm/prompt (which can't be styled, can't show
 * server errors, and block the whole page).
 *
 * - role="dialog" + aria-modal, titled by its heading, so screen readers announce it.
 * - Focus moves into the dialog when it opens, Tab stays inside it, and focus returns to the
 *   button that opened it when it closes.
 * - Escape or a click on the backdrop closes it, except while `busy` (a request is running).
 */
export default function Modal({ open, title, description, onClose, busy = false, children }) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef(null);
  // Read in the effects below without re-running them on every render.
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement;
    const panel = panelRef.current;
    const first = panel.querySelector("[data-autofocus]") ?? panel.querySelector(FOCUSABLE);
    (first ?? panel).focus();

    function onKeyDown(event) {
      if (event.key === "Escape" && !busyRef.current) {
        event.stopPropagation();
        closeRef.current();
      } else if (event.key === "Tab") {
        // Keep keyboard focus inside the dialog.
        const items = Array.from(panel.querySelectorAll(FOCUSABLE));
        if (items.length === 0) return;
        const [head, tail] = [items[0], items.at(-1)];
        if (event.shiftKey && document.activeElement === head) {
          event.preventDefault();
          tail.focus();
        } else if (!event.shiftKey && document.activeElement === tail) {
          event.preventDefault();
          head.focus();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden"; // the page behind doesn't scroll

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-slate-900/50"
        onClick={() => !busy && onClose()}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className="relative w-full max-w-lg rounded-xl bg-white p-6 shadow-xl outline-none"
      >
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold text-slate-900">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-sm text-slate-500">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            className="-m-1 rounded-md p-1 text-slate-400 hover:text-slate-600 disabled:opacity-50"
          >
            <X aria-hidden="true" className="size-5" />
          </button>
        </div>
        <div className="mt-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
