const BASE = "/api";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AnalyzeResult {
  path: string;
  files: number;
  symbols: number;
  test_files: number;
  languages: Record<string, number>;
  analyzers: Record<string, AnalyzerResult>;
}

export interface AnalyzerResult {
  summary: string;
  issues: Issue[];
  error?: string;
}

export interface Issue {
  type: string;
  file?: string;
  symbol?: string;
  line?: number;
  reason?: string;
  reasons?: string[];
  method_count?: number;
}

export interface CallerRef {
  name: string;
  file: string;
  line: number;
  covered: boolean;
}

export interface AffectedSymbol {
  name: string;
  kind: string;
  file: string;
  line_start: number;
  line_end: number;
  lang: string;
  direct_callers: CallerRef[];
  transitive_callers: CallerRef[];
  uncovered_caller_count: number;
}

export interface BlastRadiusResult {
  summary: string;
  base: string;
  has_risk: boolean;
  affected_symbols: AffectedSymbol[];
  uncovered_callers: { changed_symbol: string; caller: string; caller_file: string; caller_line: number }[];
}

export interface Symbol {
  name: string;
  kind: string;
  file: string;
  line: number;
  lang: string;
  parent_class: string | null;
  is_public: boolean;
}

export interface Config {
  exists: boolean;
  config: {
    thresholds?: {
      god_file_loc?: number;
      god_file_functions?: number;
      god_file_classes?: number;
      god_class_methods?: number;
      blast_radius_depth?: number;
    };
    ignore?: string[];
    analyzers?: { custom?: string[] };
  };
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  analyze: (path: string, analyzers = ["coverage", "observability", "solid"]) =>
    request<AnalyzeResult>("POST", "/analyze", { path, analyzers }),

  blastRadius: (path: string, base = "main", transitive_depth = 2) =>
    request<BlastRadiusResult>("POST", "/blast-radius", { path, base, transitive_depth }),

  symbolMap: (path: string, lang?: string) =>
    request<{ total: number; symbols: Symbol[] }>(
      "GET",
      `/symbol-map?path=${encodeURIComponent(path)}${lang ? `&lang=${lang}` : ""}`
    ),

  getConfig: (path: string) =>
    request<Config>("GET", `/config?path=${encodeURIComponent(path)}`),

  putConfig: (path: string, config: Config["config"]) =>
    request<{ written: boolean }>("PUT", "/config", { path, config }),

  health: () => request<{ status: string }>("GET", "/health"),
};
