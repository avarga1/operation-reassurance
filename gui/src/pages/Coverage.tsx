import { useState } from "react";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";
import { cn } from "@/lib/utils";

export function Coverage() {
  const path = useRepoPath();
  const { data, isLoading } = useAnalysis();
  const [showCovered, setShowCovered] = useState(false);

  if (!path) return <Empty />;
  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Analyzing…</div>;

  const result = data?.analyzers.coverage;
  if (!result) return <div className="p-6 text-sm text-muted-foreground">No coverage data.</div>;

  const issues = result.issues ?? [];
  const uncovered = issues.filter((i) => i.reason === "no tests");

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-bold">Coverage</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{result.summary}</p>
        </div>
        <button
          className="text-xs text-muted-foreground hover:text-foreground border border-border px-3 py-1.5 transition-colors"
          onClick={() => setShowCovered(!showCovered)}
        >
          {showCovered ? "Hide covered" : "Show covered"}
        </button>
      </div>

      <div className="border border-border">
        <div className="grid grid-cols-[1fr_auto_auto] text-xs text-muted-foreground font-medium border-b border-border px-4 py-2">
          <span>Symbol</span>
          <span className="mr-8">File</span>
          <span>Status</span>
        </div>
        {uncovered.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">
            All public symbols have test coverage.
          </div>
        ) : (
          uncovered.map((issue, i) => (
            <div
              key={i}
              className="grid grid-cols-[1fr_auto_auto] items-center px-4 py-2 border-b border-border last:border-0 hover:bg-accent/20 text-sm"
            >
              <span className="font-mono text-xs">{issue.symbol}</span>
              <span className="text-xs text-muted-foreground font-mono mr-8 truncate max-w-[300px]">
                {issue.file?.split("/").slice(-2).join("/")}:{issue.line}
              </span>
              <span className="text-xs text-destructive font-medium">✗ no tests</span>
            </div>
          ))
        )}
      </div>
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
