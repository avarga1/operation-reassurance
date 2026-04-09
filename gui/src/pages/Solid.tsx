import { useAnalysis } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";

export function Solid() {
  const path = useRepoPath();
  const { data, isLoading } = useAnalysis();

  if (!path) return <Empty />;
  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Analyzing…</div>;

  const result = data?.analyzers.solid;
  if (!result) return <div className="p-6 text-sm text-muted-foreground">No SOLID data.</div>;

  const godFiles = result.issues.filter((i) => i.type === "god_file");
  const godClasses = result.issues.filter((i) => i.type === "god_class");
  const socViolations = result.issues.filter((i) => i.type === "soc_violation");

  return (
    <div className="p-6">
      <div className="mb-4">
        <h1 className="text-lg font-bold">SOLID Health</h1>
        <p className="text-xs text-muted-foreground mt-0.5">{result.summary}</p>
      </div>

      {result.issues.length === 0 && (
        <div className="text-sm text-muted-foreground py-8 text-center border border-border">
          No SOLID issues found.
        </div>
      )}

      {godFiles.length > 0 && (
        <Section title={`God Files (${godFiles.length})`}>
          {godFiles.map((issue, i) => (
            <Row key={i}>
              <span className="font-mono text-xs truncate">
                {issue.file?.split("/").slice(-3).join("/")}
              </span>
              <span className="text-xs text-muted-foreground text-right">
                {(issue.reasons as string[])?.join(" · ")}
              </span>
            </Row>
          ))}
        </Section>
      )}

      {godClasses.length > 0 && (
        <Section title={`God Classes (${godClasses.length})`}>
          {godClasses.map((issue, i) => (
            <Row key={i}>
              <span className="font-mono text-xs">{issue.symbol}</span>
              <span className="text-xs text-muted-foreground">
                {issue.method_count} methods · {issue.file?.split("/").slice(-2).join("/")}
              </span>
            </Row>
          ))}
        </Section>
      )}

      {socViolations.length > 0 && (
        <Section title={`SoC Violations (${socViolations.length})`}>
          {socViolations.map((issue, i) => (
            <div key={i} className="px-4 py-2.5 border-b border-border last:border-0 hover:bg-accent/20">
              <div className="font-mono text-xs truncate mb-0.5">
                {issue.file?.split("/").slice(-3).join("/")}
              </div>
              <div className="text-xs text-muted-foreground">{issue.reason}</div>
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
        {title}
      </h2>
      <div className="border border-border divide-y divide-border">{children}</div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-2 hover:bg-accent/20 gap-4">
      {children}
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
