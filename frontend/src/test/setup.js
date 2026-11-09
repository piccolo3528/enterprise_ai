import "@testing-library/jest-dom/vitest"; // adds matchers like toBeInTheDocument()
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount rendered components after each test so tests don't see each other's DOM.
afterEach(cleanup);
