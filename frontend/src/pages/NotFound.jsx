import { FileQuestion } from "lucide-react";
import { Link } from "react-router";

import EmptyState from "../components/ui/EmptyState";

export default function NotFound() {
  return (
    <EmptyState
      icon={FileQuestion}
      title="Page not found"
      description="This page doesn't exist, or hasn't been built yet."
      action={
        <Link
          to="/dashboard"
          className="rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Go to the dashboard
        </Link>
      }
    />
  );
}
