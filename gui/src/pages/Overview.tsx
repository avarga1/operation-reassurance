import { useAnalysis } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";

const LANG_COLORS: Record<string, string> = {
  python: "bg-blue-500",
  dart: "bg-cyan-500",
  typescript: "bg-yellow-500",
  javascript: "bg-yellow-400",
  rust: "bg-orange-500",
};

export function Overview() {
  const path = useRepoPath();
  const { data, isLoading, error } = useAnalysis();

  if (!path) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Select a repo to get started.
      </div>
    );
  }

  if (isLoading) return <PageSkeleton />;
  if (error || !data) return <ErrorState message={String(error)} />;

  const totalIssues = Object.values(data.analyzers).reduce(
    (sum, a) => sum + (a.issues?.length ?? 0),
    0
  );
  const langTotal = Object.values(data.languages).reduce((s, n) => s + n, 0);
  const coverageSummary = data.analyzers.coverage?.summary ?? "—";
  const solidSummary = data.analyzers.solid?.summary ?? "—";
  const obsSummary = data.analyzers.observability?.summary ?? "—";

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-lg font-bold truncate">{path.split("/").pop()}</h1>
        <p className="text-xs text-muted-foreground font-mono mt-0.5">{path}</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-px border border-border mb-6">
        {[
          { label: "Files", value: data.files },
          { label: "Symbols", value: data.symbols },
          { label: "Test files", value: data.test_files },
          { label: "Issues", value: totalIssues },
        ].map(({ label, value }) => (
          <div key={label} className="bg-card px-4 py-3">
            <div className="text-2xl font-bold tabular-nums">{value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Language breakdown */}
      <div className="mb-6">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Languages
        </h2>
        <div className="flex h-2 rounded-none overflow-hidden border border-border mb-2">
          {Object.entries(data.languages).map(([lang, count]) => (
            <div
              key={lang}
              className={LANG_COLORS[lang] ?? "bg-gray-400"}
              style={{ width: `${(count / langTotal) * 100}%` }}
              title={`${lang}: ${count} files`}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          {Object.entries(data.languages).map(([lang, count]) => (
            <div key={lang} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <div className={`w-2 h-2 ${LANG_COLORS[lang] ?? "bg-gray-400"}`} />
              <span>{lang}</span>
              <span className="text-foreground font-medium">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Analyzer summaries */}
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
        Analysis
      </h2>
      <div className="border border-border divide-y divide-border">
        {[
          { name: "Coverage", summary: coverageSummary, href: "/coverage" },
          { name: "Observability", summary: obsSummary, href: "/observability" },
          { name: "SOLID", summary: solidSummary, href: "/solid" },
        ].map(({ name, summary, href }) => (
          <a
            key={name}
            href={href}
            className="flex items-center justify-between px-4 py-3 hover:bg-accent/30 transition-colors"
          >
            <span className="text-sm font-medium">{name}</span>
            <span className="text-xs text-muted-foreground">{summary}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="p-6 max-w-4xl animate-pulse">
      <div className="h-5 bg-muted w-48 mb-1" />
      <div className="h-3 bg-muted w-72 mb-6" />
      <div className="grid grid-cols-4 gap-px border border-border mb-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-card px-4 py-3">
            <div className="h-8 bg-muted w-16 mb-1" />
            <div className="h-3 bg-muted w-12" />
          </div>
        ))}
      </div>
      <div className="h-2 bg-muted mb-4" />
      <div className="border border-border divide-y divide-border">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="px-4 py-3 flex justify-between">
            <div className="h-4 bg-muted w-24" />
            <div className="h-4 bg-muted w-48" />
          </div>
        ))}
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="p-6 text-sm text-destructive">
      <p className="font-medium">Analysis failed</p>
      <p className="text-xs mt-1 font-mono text-muted-foreground">{message}</p>
    </div>
  );
}
