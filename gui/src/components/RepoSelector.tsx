import { useState, useEffect } from "react";
import { FolderOpen, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "reassure:recent_repos";
const ACTIVE_KEY = "reassure:active_paths";
const MAX_RECENT = 8;

function getRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function addRecent(path: string) {
  const recent = [path, ...getRecent().filter((p) => p !== path)].slice(0, MAX_RECENT);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(recent));
}

// Global multi-path state
let _listeners: Array<(paths: string[]) => void> = [];
let _currentPaths: string[] = (() => {
  try {
    const saved = JSON.parse(localStorage.getItem(ACTIVE_KEY) ?? "null");
    if (Array.isArray(saved) && saved.length > 0) return saved;
  } catch { /* ignore */ }
  const env = import.meta.env.VITE_REASSURE_PATH as string | undefined;
  const first = getRecent()[0] ?? env ?? "";
  return first ? [first] : [];
})();

function notify() {
  localStorage.setItem(ACTIVE_KEY, JSON.stringify(_currentPaths));
  _listeners.forEach((l) => l([..._currentPaths]));
}

export function useRepoPaths(): string[] {
  const [paths, setPaths] = useState<string[]>(_currentPaths);
  useEffect(() => {
    _listeners.push(setPaths);
    return () => { _listeners = _listeners.filter((l) => l !== setPaths); };
  }, []);
  return paths;
}

/** Convenience hook — returns the first active path (backward compat). */
export function useRepoPath(): string {
  return useRepoPaths()[0] ?? "";
}

function addPath(path: string) {
  if (!_currentPaths.includes(path)) {
    _currentPaths = [..._currentPaths, path];
  }
  addRecent(path);
  notify();
}

function removePath(path: string) {
  _currentPaths = _currentPaths.filter((p) => p !== path);
  notify();
}

function setGlobalPath(path: string) {
  _currentPaths = [path];
  addRecent(path);
  notify();
}

// ── PathRow ────────────────────────────────────────────────────────────────────

function PathRow({ path, onRemove }: { path: string; onRemove: () => void }) {
  return (
    <div className="flex items-center gap-1 group px-2 py-1 hover:bg-accent/40 transition-colors">
      <FolderOpen className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate font-mono text-[11px] text-foreground" title={path}>
        {path.split("/").slice(-2).join("/")}
      </span>
      <button
        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
        onClick={onRemove}
        aria-label="Remove repo"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ── AddPathInput ───────────────────────────────────────────────────────────────

function AddPathInput({ onDone }: { onDone: () => void }) {
  const [draft, setDraft] = useState("");
  const recent = getRecent().filter((r) => !_currentPaths.includes(r));

  function submit() {
    const trimmed = draft.trim();
    if (trimmed) addPath(trimmed);
    onDone();
  }

  return (
    <div className="flex flex-col gap-0.5 px-1 pb-1">
      <input
        autoFocus
        className="w-full text-xs font-mono bg-background border border-border px-2 py-1 outline-none focus:ring-1 focus:ring-ring"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") onDone();
        }}
        placeholder="/path/to/repo"
      />
      {recent.length > 0 && (
        <div className="flex flex-col gap-0">
          {recent.map((r) => (
            <button
              key={r}
              className="text-left text-[11px] text-muted-foreground hover:text-foreground truncate px-1 py-0.5"
              onClick={() => { addPath(r); onDone(); }}
            >
              {r}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── RepoSelector ───────────────────────────────────────────────────────────────

export function RepoSelector() {
  const paths = useRepoPaths();
  const [adding, setAdding] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");

  function startEdit(idx: number) {
    setEditDraft(paths[idx]);
    setEditingIdx(idx);
    setAdding(false);
  }

  function submitEdit() {
    const trimmed = editDraft.trim();
    if (trimmed && editingIdx !== null) {
      const next = [..._currentPaths];
      next[editingIdx] = trimmed;
      _currentPaths = next;
      addRecent(trimmed);
      notify();
    }
    setEditingIdx(null);
  }

  return (
    <div className="flex flex-col gap-0">
      {paths.length === 0 && !adding && (
        <button
          className={cn(
            "w-full flex items-center gap-2 px-2 py-1.5 text-left text-[12px] transition-colors",
            "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setAdding(true)}
        >
          <FolderOpen className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate font-mono">Select repo…</span>
        </button>
      )}

      {paths.map((p, i) =>
        editingIdx === i ? (
          <div key={p} className="flex flex-col gap-0.5 px-1 pb-0.5">
            <input
              autoFocus
              className="w-full text-xs font-mono bg-background border border-border px-2 py-1 outline-none focus:ring-1 focus:ring-ring"
              value={editDraft}
              onChange={(e) => setEditDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitEdit();
                if (e.key === "Escape") setEditingIdx(null);
              }}
            />
          </div>
        ) : (
          <div key={p} className="flex items-center gap-1 group px-2 py-1 hover:bg-accent/40 transition-colors">
            <FolderOpen className="h-3 w-3 shrink-0 text-muted-foreground" />
            <button
              className="flex-1 truncate font-mono text-[11px] text-foreground text-left"
              title={p}
              onClick={() => startEdit(i)}
            >
              {p.split("/").slice(-2).join("/")}
            </button>
            <button
              className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => removePath(p)}
              aria-label="Remove repo"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      )}

      {adding && <AddPathInput onDone={() => setAdding(false)} />}

      {!adding && editingIdx === null && (
        <button
          className="flex items-center gap-1.5 px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors"
          onClick={() => setAdding(true)}
        >
          <Plus className="h-3 w-3" />
          <span>Add repo</span>
        </button>
      )}
    </div>
  );
}
