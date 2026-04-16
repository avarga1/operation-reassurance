import { useState, useRef } from "react";
import { Code2, Lock, ExternalLink, RefreshCw, X, AlertTriangle } from "lucide-react";
import { useKaiAuth } from "@/hooks/useKaiAuth";
import { useRepoPaths } from "@/components/RepoSelector";
import { cn } from "@/lib/utils";

export function Develop() {
  const auth = useKaiAuth();
  const paths = useRepoPaths();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [certWarningDismissed, setCertWarningDismissed] = useState(false);

  if (auth.status === "verifying") return <Spinner />;
  if (auth.status !== "valid") return <LockScreen auth={auth} />;

  // Build the studio URL — pass the first active repo as the folder hint
  // (only works if the path exists on the kai server; graceful fallback otherwise)
  const folder = paths[0] ?? "";
  const studioUrl = folder
    ? `${auth.studioUrl}/?folder=${encodeURIComponent(folder)}`
    : auth.studioUrl!;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 h-9 border-b border-border bg-background shrink-0">
        <Code2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs font-mono text-muted-foreground truncate flex-1">
          {auth.studioUrl}
          {folder && <span className="text-foreground"> · {folder.split("/").slice(-1)[0]}</span>}
        </span>
        <button
          className="p-1 hover:text-foreground text-muted-foreground transition-colors"
          title="Reload"
          onClick={() => iframeRef.current?.contentWindow?.location.reload()}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        <a
          href={studioUrl}
          target="_blank"
          rel="noreferrer"
          className="p-1 hover:text-foreground text-muted-foreground transition-colors"
          title="Open in new tab"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
        <button
          className="p-1 hover:text-destructive text-muted-foreground transition-colors"
          title="Disconnect"
          onClick={auth.clear}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Self-signed cert warning banner */}
      {!certWarningDismissed && (
        <div className="flex items-center gap-3 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 text-xs text-amber-700 dark:text-amber-400 shrink-0">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>
            Kai Studio uses a self-signed certificate. If the IDE doesn&apos;t load,{" "}
            <a
              href={auth.studioUrl!}
              target="_blank"
              rel="noreferrer"
              className="underline font-medium"
            >
              open it in a new tab
            </a>{" "}
            to accept the cert, then reload here.
          </span>
          <button
            className="ml-auto shrink-0 hover:text-foreground"
            onClick={() => setCertWarningDismissed(true)}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* IDE iframe */}
      <iframe
        ref={iframeRef}
        src={studioUrl}
        className="flex-1 w-full border-0"
        allow="clipboard-read; clipboard-write"
        title="Kai Studio"
      />
    </div>
  );
}

// ── Lock screen ────────────────────────────────────────────────────────────────

function LockScreen({ auth }: { auth: ReturnType<typeof useKaiAuth> }) {
  const [draft, setDraft] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (draft.trim()) await auth.verify(draft.trim());
  }

  const isError = auth.status === "invalid";
  const isUnconfigured = auth.status === "unconfigured";

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-8">
      <div className="flex flex-col items-center gap-3 text-center max-w-sm">
        <div className="flex items-center justify-center w-12 h-12 border border-border bg-accent/30">
          <Code2 className="h-6 w-6 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-sm font-bold tracking-tight">Kai Studio</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Web-native development environment. Enter your API key to unlock.
          </p>
        </div>
      </div>

      {isUnconfigured ? (
        <div className="flex items-center gap-2 text-xs text-amber-600 border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 px-4 py-3 max-w-sm w-full">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>Kai Studio is not configured on this reassure server. Set <code className="font-mono">KAI_API_KEY_HASH</code> to enable it.</span>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3 w-full max-w-sm">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Lock className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="password"
                autoFocus
                placeholder="API key"
                className={cn(
                  "w-full pl-8 pr-3 py-2 text-sm font-mono bg-background border outline-none focus:ring-1 focus:ring-ring",
                  isError ? "border-destructive" : "border-border"
                )}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={!draft.trim() || auth.status === "verifying"}
              className="px-4 py-2 text-sm border border-border hover:bg-accent/50 transition-colors disabled:opacity-40"
            >
              {auth.status === "verifying" ? "…" : "Unlock"}
            </button>
          </div>
          {isError && (
            <p className="text-xs text-destructive">Invalid key. Try again.</p>
          )}
        </form>
      )}

      <p className="text-[11px] text-muted-foreground text-center max-w-xs">
        Kai Studio is a private component of reassure. Contact the team to request access.
      </p>
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground text-sm gap-2">
      <RefreshCw className="h-4 w-4 animate-spin" />
      Connecting…
    </div>
  );
}
