import { BrainCircuit } from "lucide-react";

const SIZES = {
  sm: { tile: "size-7 rounded-lg", icon: "size-4" },
  md: { tile: "size-8 rounded-lg", icon: "size-5" },
  lg: { tile: "size-10 rounded-xl", icon: "size-6" },
  xl: { tile: "size-14 rounded-2xl", icon: "size-8" },
};

/**
 * The app's logo: a brain-circuit icon on an indigo tile. One component, so the sidebar, the
 * sign-in pages and the loader always show the same mark. `animated` turns on the "thinking"
 * animation (see index.css); decorative either way (aria-hidden).
 */
export default function BrandMark({ size = "md", animated = false, className = "" }) {
  const { tile, icon } = SIZES[size];
  return (
    <span aria-hidden="true" className={`relative inline-flex shrink-0 ${tile} ${className}`}>
      {animated && <span className={`brand-halo absolute inset-0 bg-indigo-400 ${tile}`} />}
      <span
        className={`relative flex size-full items-center justify-center overflow-hidden bg-indigo-600 ${tile} ${
          animated ? "brand-breathe" : ""
        }`}
      >
        <BrainCircuit className={`${icon} ${animated ? "text-white/40" : "text-white"}`} />
        {animated && <BrainCircuit className={`brand-scan absolute ${icon} text-white`} />}
      </span>
    </span>
  );
}
