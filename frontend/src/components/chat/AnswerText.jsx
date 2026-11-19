import Markdown from "react-markdown";

const CITATION = /\[(\d{1,3})\](?!\()/g;

/** "[2]" -> "[2](#cite-2)", so the Markdown renderer hands each citation to our link component. */
export function linkCitations(text) {
  return text.replace(CITATION, "[$1](#cite-$1)");
}

export function CitationChip({ number, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`Show source ${number}`}
      className={`mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1 align-text-top text-xs font-semibold ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-indigo-600 ${
        active
          ? "bg-indigo-600 text-white ring-indigo-600"
          : "bg-indigo-50 text-indigo-700 ring-indigo-200 hover:bg-indigo-100"
      }`}
    >
      {number}
    </button>
  );
}

/**
 * The model's answer as Markdown. Raw HTML is never rendered (react-markdown drops it unless a
 * plugin opts in), so text from documents or the model can't inject markup or scripts.
 * Citation numbers become buttons that open the source in the side panel.
 */
export default function AnswerText({ text, citations, selected, onCite }) {
  const numbers = new Set(citations.map((c) => c.number));
  const components = {
    a: ({ href, children }) => {
      const match = href?.match(/^#cite-(\d+)$/);
      if (match && numbers.has(Number(match[1]))) {
        const n = Number(match[1]);
        return <CitationChip number={n} active={selected === n} onClick={() => onCite(n)} />;
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline">
          {children}
        </a>
      );
    },
    p: ({ children }) => <p className="leading-relaxed">{children}</p>,
    ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
    strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
    h1: ({ children }) => <h3 className="font-semibold text-slate-900">{children}</h3>,
    h2: ({ children }) => <h3 className="font-semibold text-slate-900">{children}</h3>,
    h3: ({ children }) => <h3 className="font-semibold text-slate-900">{children}</h3>,
    code: ({ children }) => (
      <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">{children}</code>
    ),
  };
  return (
    <div className="space-y-2 text-sm text-slate-800">
      <Markdown components={components}>{linkCitations(text)}</Markdown>
    </div>
  );
}
