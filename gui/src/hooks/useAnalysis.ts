import { useQuery } from "@tanstack/react-query";
import { api, AnalyzeResult, AnalyzerResult } from "@/api/client";
import { useRepoPath, useRepoPaths } from "@/components/RepoSelector";

function mergeLanguages(results: AnalyzeResult[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of results) {
    for (const [lang, count] of Object.entries(r.languages)) {
      out[lang] = (out[lang] ?? 0) + count;
    }
  }
  return out;
}

function mergeAnalyzers(results: AnalyzeResult[]): Record<string, AnalyzerResult> {
  const names = new Set(results.flatMap((r) => Object.keys(r.analyzers)));
  const out: Record<string, AnalyzerResult> = {};
  for (const name of names) {
    const parts = results.filter((r) => r.analyzers[name]);
    const summaries = parts.map((r) => {
      const label = r.path.split("/").slice(-1)[0];
      return `${label}: ${r.analyzers[name].summary}`;
    });
    const issues = parts.flatMap((r) => r.analyzers[name].issues ?? []);
    out[name] = { summary: summaries.join(" · "), issues };
  }
  return out;
}

export interface MergedAnalysis {
  files: number;
  symbols: number;
  test_files: number;
  languages: Record<string, number>;
  analyzers: Record<string, AnalyzerResult>;
  /** Per-repo raw results — use for multi-repo breakdowns. */
  repos: AnalyzeResult[];
}

/** Returns a merged view across all active repo paths. */
export function useAnalysis() {
  const paths = useRepoPaths();
  return useQuery({
    queryKey: ["analysis", ...paths],
    queryFn: () => api.analyzeMulti(paths),
    enabled: paths.length > 0,
    select: (results): MergedAnalysis => ({
      files: results.reduce((n, r) => n + r.files, 0),
      symbols: results.reduce((n, r) => n + r.symbols, 0),
      test_files: results.reduce((n, r) => n + r.test_files, 0),
      languages: mergeLanguages(results),
      analyzers: mergeAnalyzers(results),
      repos: results,
    }),
  });
}

/** Blast-radius stays single-path (git-diff is per-repo). */
export function useBlastRadius(base = "main") {
  const path = useRepoPath();
  return useQuery({
    queryKey: ["blast-radius", path, base],
    queryFn: () => api.blastRadius(path, base),
    enabled: !!path,
  });
}

/** Config stays single-path. */
export function useConfig() {
  const path = useRepoPath();
  return useQuery({
    queryKey: ["config", path],
    queryFn: () => api.getConfig(path),
    enabled: !!path,
  });
}
