import { useState, useRef, useEffect } from "react";
import { Code2, Lock, ExternalLink, RefreshCw, X, AlertTriangle, Maximize2 } from "lucide-react";
import { useKaiAuth } from "@/hooks/useKaiAuth";
import { useRepoPaths } from "@/components/RepoSelector";
import { cn } from "@/lib/utils";

export function Develop() {
  const auth = useKaiAuth();
  const paths = useRepoPaths();
  const iframeRef = useRef<HTMLIFrameElement>(null!) as React.RefObject<HTMLIFrameElement>;
  const [embedFailed, setEmbedFailed] = useState(false);
  const [embedMode, setEmbedMode] = useState(false);

  if (auth.status === "verifying") return <Spinner />;
  if (auth.status !== "valid") return <LockScreen auth={auth} />;

  const studioUrl = auth.studioUrl!;
  const repoLabel = paths[0]?.split("/").slice(-1)[0] ?? "";

  function launch() {
    window.open(studioUrl, "kai-studio", "noopener,noreferrer");
  }

  // Try embed — if it doesn't load within 4s, show the fallback
  function tryEmbed() {
    setEmbedFailed(false);
    setEmbedMode(true);
  }

  if (embedMode && !embedFailed) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 px-3 h-9 border-b border-border bg-background shrink-0">
          <Code2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="text-xs font-mono text-muted-foreground truncate flex-1">
            {studioUrl}
            {repoLabel && <span className="text-foreground"> · {repoLabel}</span>}
          </span>
          <button
            className="p-1 hover:text-foreground text-muted-foreground transition-colors"
            title="Reload"
            onClick={() => iframeRef.current?.contentWindow?.location.reload()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button
            className="p-1 hover:text-foreground text-muted-foreground transition-colors"
            title="Pop out"
            onClick={launch}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
          <button
            className="p-1 hover:text-foreground text-muted-foreground transition-colors"
            title="Exit embed"
            onClick={() => setEmbedMode(false)}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <EmbedProbe
          studioUrl={studioUrl}
          iframeRef={iframeRef}
          onFail={() => setEmbedFailed(true)}
        />
      </div>
    );
  }

  // ── Launcher (primary) ─────────────────────────────────────────────────────
  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 px-8">
      <div className="flex flex-col items-center gap-4 text-center max-w-sm">
        <div className="flex items-center justify-center w-16 h-16 border border-border bg-accent/20">
          <Code2 className="h-8 w-8 text-foreground" />
        </div>
        <div>
          <h1 className="text-base font-bold tracking-tight">Kai Studio</h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono">{studioUrl}</p>
          {repoLabel && (
            <p className="text-xs text-muted-foreground mt-0.5">
              workspace · <span className="text-foreground font-medium">{repoLabel}</span>
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 w-full max-w-xs">
        <button
          onClick={launch}
          className="flex items-center justify-center gap-2 w-full py-2.5 text-sm font-medium border border-border bg-foreground text-background hover:opacity-90 transition-opacity"
        >
          <ExternalLink className="h-4 w-4" />
          Launch Kai Studio
        </button>
        <button
          onClick={tryEmbed}
          className="flex items-center justify-center gap-2 w-full py-2 text-xs text-muted-foreground border border-border hover:bg-accent/50 transition-colors"
        >
          Try embedded view
        </button>
      </div>

      <button
        className="text-[11px] text-muted-foreground hover:text-destructive transition-colors"
        onClick={auth.clear}
      >
        Disconnect
      </button>
    </div>
  );
}

// ── Embed probe — detects if iframe actually loaded ────────────────────────────

function EmbedProbe({
  studioUrl,
  iframeRef,
  onFail,
}: {
  studioUrl: string;
  iframeRef: React.RefObject<HTMLIFrameElement>;
  onFail: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onFail, 5000);
    return () => clearTimeout(t);
  }, [onFail]);

  return (
    <iframe
      ref={iframeRef}
      src={studioUrl}
      className="flex-1 w-full border-0"
      allow="clipboard-read; clipboard-write"
      title="Kai Studio"
      onLoad={() => {
        // If the iframe loads but is blank (cross-origin block), we can't detect it —
        // rely on the timeout as the fallback signal.
      }}
    />
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
          <span>Kai Studio is not configured on this server. Set <code className="font-mono">KAI_API_KEY_HASH</code> to enable it.</span>
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
