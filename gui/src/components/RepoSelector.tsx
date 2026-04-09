import { useState, useEffect } from "react";
import { FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "reassure:recent_repos";
const MAX_RECENT = 5;

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

// Global repo path state — simple module-level for now
let _listeners: Array<(path: string) => void> = [];
let _currentPath = getRecent()[0] ?? "";

export function useRepoPath() {
  const [path, setPath] = useState(_currentPath);
  useEffect(() => {
    _listeners.push(setPath);
    return () => {
      _listeners = _listeners.filter((l) => l !== setPath);
    };
  }, []);
  return path;
}

function setGlobalPath(path: string) {
  _currentPath = path;
  addRecent(path);
  _listeners.forEach((l) => l(path));
}

export function RepoSelector() {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(_currentPath);
  const recent = getRecent();
  const current = _currentPath;

  function submit() {
    if (draft.trim()) {
      setGlobalPath(draft.trim());
    }
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex flex-col gap-1">
        <input
          autoFocus
          className="w-full text-xs font-mono bg-background border border-border px-2 py-1 outline-none focus:ring-1 focus:ring-ring"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setEditing(false);
          }}
          placeholder="/path/to/repo"
        />
        {recent.length > 0 && (
          <div className="flex flex-col gap-0.5">
            {recent.map((r) => (
              <button
                key={r}
                className="text-left text-[11px] text-muted-foreground hover:text-foreground truncate px-1"
                onClick={() => { setDraft(r); setGlobalPath(r); setEditing(false); }}
              >
                {r}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      className={cn(
        "w-full flex items-center gap-2 px-2 py-1.5 text-left text-[12px] transition-colors",
        "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
      )}
      onClick={() => { setDraft(current); setEditing(true); }}
    >
      <FolderOpen className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate font-mono">
        {current ? current.split("/").slice(-2).join("/") : "Select repo…"}
      </span>
    </button>
  );
}
