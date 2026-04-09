import { useAnalysis } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";

export function Observability() {
  const path = useRepoPath();
  const { data, isLoading } = useAnalysis();

  if (!path) return <Empty />;
  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Analyzing…</div>;

  const result = data?.analyzers.observability;
  if (!result) return <div className="p-6 text-sm text-muted-foreground">No observability data.</div>;

  const darkModules = result.issues.filter((i) => i.type === "dark_module");
  const darkFunctions = result.issues.filter((i) => i.type === "dark_function");

  return (
    <div className="p-6">
      <div className="mb-4">
        <h1 className="text-lg font-bold">Observability</h1>
        <p className="text-xs text-muted-foreground mt-0.5">{result.summary}</p>
      </div>

      {/* Dark modules */}
      {darkModules.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Dark modules ({darkModules.length})
          </h2>
          <div className="border border-border divide-y divide-border">
            {darkModules.map((issue, i) => (
              <div key={i} className="px-4 py-2 text-sm font-mono text-xs flex items-center justify-between">
                <span>{issue.file?.split("/").slice(-3).join("/")}</span>
                <span className="text-destructive text-[11px]">zero instrumentation</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dark functions */}
      {darkFunctions.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Dark functions ({darkFunctions.length})
          </h2>
          <div className="border border-border">
            <div className="grid grid-cols-[1fr_auto] text-xs text-muted-foreground font-medium border-b border-border px-4 py-2">
              <span>Symbol</span>
              <span>File</span>
            </div>
            {darkFunctions.map((issue, i) => (
              <div key={i} className="grid grid-cols-[1fr_auto] px-4 py-2 border-b border-border last:border-0 hover:bg-accent/20">
                <span className="text-xs font-mono">{issue.symbol}</span>
                <span className="text-xs text-muted-foreground font-mono">
                  {issue.file?.split("/").slice(-2).join("/")}:{issue.line}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {darkModules.length === 0 && darkFunctions.length === 0 && (
        <div className="text-sm text-muted-foreground py-8 text-center border border-border">
          All functions have observability instrumentation.
        </div>
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
      Select a repo to analyze.
    </div>
  );
}
