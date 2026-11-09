import { CircleAlert, RefreshCw } from "lucide-react";

import Button from "./Button";

/**
 * Shows an ApiError (or any message). The request ID lets a screenshot of the error be matched
 * to the exact backend log line.
 */
export default function ErrorBanner({ title = "Something went wrong", error, onRetry }) {
  const message = typeof error === "string" ? error : error?.message;
  const requestId = typeof error === "object" ? error?.requestId : null;

  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4">
      <div className="flex gap-3">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-red-500" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-red-800">{title}</h3>
          {message && <p className="mt-1 text-sm text-red-700">{message}</p>}
          {requestId && (
            <p className="mt-2 font-mono text-xs text-red-600/80">Reference: {requestId}</p>
          )}
        </div>
        {onRetry && (
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
