import { CircleAlert, CircleCheck, UploadCloud, X } from "lucide-react";
import { useId, useRef, useState } from "react";

import { ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, uploadDocument } from "../../api/documents";
import { formatBytes } from "../../utils/format";

/** Quick checks in the browser, so an obvious mistake doesn't cost an upload. */
export function precheck(file) {
  const ext = file.name.includes(".") ? file.name.split(".").at(-1).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return "Only PDF, Word (.docx), Markdown (.md) and text (.txt) files can be uploaded.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The file is larger than ${MAX_UPLOAD_MB} MB.`;
  return null;
}

let nextKey = 0;

/**
 * Drop files here or click to choose them. Files upload one at a time, each with its own
 * progress bar and its own error, so one bad file doesn't hide what happened to the others.
 * `onUploaded(document)` runs after each successful upload.
 */
export default function UploadDropzone({ kbId, onUploaded }) {
  const inputRef = useRef(null);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState([]); // {key, name, size, progress, state, error}
  const queue = useRef(Promise.resolve());

  function update(key, changes) {
    setUploads((list) => list.map((u) => (u.key === key ? { ...u, ...changes } : u)));
  }

  function addFiles(files) {
    for (const file of files) {
      const key = ++nextKey;
      const problem = precheck(file);
      setUploads((list) => [
        ...list,
        {
          key,
          name: file.name,
          size: file.size,
          progress: 0,
          state: problem ? "error" : "waiting",
          error: problem,
        },
      ]);
      if (problem) continue;
      // Chain onto the queue: uploads run one after another, never in parallel.
      queue.current = queue.current.then(async () => {
        update(key, { state: "uploading" });
        try {
          const document = await uploadDocument(kbId, file, {
            onProgress: (progress) => update(key, { progress }),
          });
          update(key, { state: "done", progress: 1 });
          onUploaded?.(document);
        } catch (err) {
          update(key, { state: "error", error: err.message });
        }
      });
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer?.files ?? []));
  }

  const finished = uploads.filter((u) => u.state === "done" || u.state === "error");

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        aria-describedby={hintId}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault(); // without this the browser opens the dropped file itself
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-white hover:bg-slate-50"
        }`}
      >
        <UploadCloud aria-hidden="true" className="size-8 text-slate-400" />
        <p className="mt-2 text-sm font-medium text-slate-900">
          Drop files here, or <span className="text-indigo-600">choose files</span>
        </p>
        <p id={hintId} className="mt-1 text-xs text-slate-500">
          PDF, Word (.docx), Markdown or text · up to {MAX_UPLOAD_MB} MB each
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.map((e) => `.${e}`).join(",")}
          className="hidden"
          data-testid="file-input"
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            e.target.value = ""; // choosing the same file again still triggers onChange
          }}
        />
      </div>

      {uploads.length > 0 && (
        <ul aria-label="Uploads" className="space-y-2">
          {uploads.map((u) => (
            <li
              key={u.key}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                {u.state === "done" && (
                  <CircleCheck aria-hidden="true" className="size-4 text-emerald-600" />
                )}
                {u.state === "error" && (
                  <CircleAlert aria-hidden="true" className="size-4 text-red-500" />
                )}
                <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{u.name}</span>
                <span className="text-xs text-slate-500">{formatBytes(u.size)}</span>
                <span className="w-20 text-right text-xs text-slate-500">
                  {u.state === "waiting" && "Waiting…"}
                  {u.state === "uploading" && `${Math.round(u.progress * 100)}%`}
                  {u.state === "done" && "Uploaded"}
                  {u.state === "error" && "Not uploaded"}
                </span>
              </div>
              {u.state === "uploading" && (
                <div
                  role="progressbar"
                  aria-label={`Uploading ${u.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(u.progress * 100)}
                  className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"
                >
                  <div
                    className="h-full bg-indigo-500 transition-all"
                    style={{ width: `${Math.round(u.progress * 100)}%` }}
                  />
                </div>
              )}
              {u.error && <p className="mt-1 text-xs text-red-600">{u.error}</p>}
            </li>
          ))}
        </ul>
      )}
      {finished.length > 0 && finished.length === uploads.length && (
        <button
          type="button"
          onClick={() => setUploads([])}
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800"
        >
          <X aria-hidden="true" className="size-3.5" />
          Clear this list
        </button>
      )}
    </div>
  );
}
