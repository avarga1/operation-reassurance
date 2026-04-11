import { useState, useCallback } from "react";
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  Background,
  Controls,
  type Node,
  type Edge,
  type Connection,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useBlastRadius } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";
import type { AffectedSymbol } from "@/api/client";

// ── Graph builder ─────────────────────────────────────────────────────────────

function buildGraph(symbols: AffectedSymbol[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const seen = new Set<string>();

  let x = 0;
  for (const sym of symbols) {
    const symId = `changed:${sym.name}`;
    if (!seen.has(symId)) {
      nodes.push({
        id: symId,
        data: { label: sym.name, file: sym.file, line: sym.line_start },
        position: { x, y: 0 },
        style: {
          background: "#d97706",
          color: "#fff",
          border: "none",
          borderRadius: 0,
          fontSize: 11,
          padding: "4px 8px",
          fontFamily: "monospace",
        },
      });
      seen.add(symId);
      x += 220;
    }

    let dy = 0;
    for (const caller of [...sym.direct_callers, ...sym.transitive_callers]) {
      const callerId = `caller:${caller.name}:${caller.file}`;
      const isTransitive = !sym.direct_callers.includes(caller);
      if (!seen.has(callerId)) {
        nodes.push({
          id: callerId,
          data: { label: caller.name, file: caller.file, line: caller.line },
          position: { x: x - 220, y: 80 + dy },
          style: {
            background: caller.covered ? "#16a34a" : "#dc2626",
            color: "#fff",
            border: "none",
            borderRadius: 0,
            fontSize: 11,
            padding: "4px 8px",
            fontFamily: "monospace",
            opacity: isTransitive ? 0.7 : 1,
          },
        });
        seen.add(callerId);
        dy += 60;
      }
      edges.push({
        id: `e:${symId}:${callerId}`,
        source: symId,
        target: callerId,
        animated: !caller.covered,
        style: { stroke: caller.covered ? "#16a34a" : "#dc2626", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: caller.covered ? "#16a34a" : "#dc2626" },
      });
    }
  }

  return { nodes, edges };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BlastRadius() {
  const path = useRepoPath();
  const [base, setBase] = useState("main");
  const [inputBase, setInputBase] = useState("main");
  const { data, isLoading, refetch } = useBlastRadius(base);

  const { nodes: initialNodes, edges: initialEdges } = data?.affected_symbols.length
    ? buildGraph(data.affected_symbols)
    : { nodes: [], edges: [] };

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const onConnect = useCallback((c: Connection) => setEdges((eds) => addEdge(c, eds)), [setEdges]);

  if (!path) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Select a repo to analyze.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border shrink-0">
        <h1 className="text-sm font-bold">Blast Radius</h1>
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-xs text-muted-foreground">vs</span>
          <input
            className="text-xs font-mono bg-background border border-border px-2 py-1 w-28 outline-none focus:ring-1 focus:ring-ring"
            value={inputBase}
            onChange={(e) => setInputBase(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { setBase(inputBase); refetch(); }}}
            placeholder="main"
          />
          <button
            className="text-xs border border-border px-3 py-1 hover:bg-accent/50 transition-colors"
            onClick={() => { setBase(inputBase); refetch(); }}
          >
            Analyze
          </button>
        </div>
        {data && (
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>{data.summary}</span>
            {data.has_risk && (
              <span className="text-destructive font-medium">⚠ uncovered callers</span>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-6 py-2 border-b border-border bg-muted/30 text-[11px] text-muted-foreground shrink-0">
        <LegendItem color="bg-amber-500" label="Changed" />
        <LegendItem color="bg-green-600" label="Covered caller" />
        <LegendItem color="bg-red-600" label="Uncovered caller (risky)" />
        <span className="ml-auto">Dashed edge = no test coverage on that path</span>
      </div>

      {/* Graph */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
          Analyzing diff vs {base}…
        </div>
      ) : !data || data.affected_symbols.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
          No changed symbols vs <span className="font-mono ml-1">{base}</span>.
        </div>
      ) : (
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
            className="bg-background"
          >
            <Background color="var(--border)" gap={20} />
            <Controls className="[&>button]:rounded-none [&>button]:border-border" />
          </ReactFlow>
        </div>
      )}

      {/* Uncovered callers table */}
      {data?.uncovered_callers && data.uncovered_callers.length > 0 && (
        <div className="border-t border-border shrink-0 max-h-48 overflow-y-auto">
          <div className="px-6 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider border-b border-border">
            Uncovered callers — {data.uncovered_callers.length} at risk
          </div>
          {data.uncovered_callers.map((c, i) => (
            <div key={i} className="flex items-center gap-4 px-6 py-2 border-b border-border last:border-0 text-xs hover:bg-accent/20">
              <span className="font-mono text-destructive">{c.caller}</span>
              <span className="text-muted-foreground">calls</span>
              <span className="font-mono">{c.changed_symbol}</span>
              <span className="text-muted-foreground font-mono ml-auto">
                {c.caller_file.split("/").slice(-2).join("/")}:{c.caller_line}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2.5 h-2.5 ${color}`} />
      <span>{label}</span>
    </div>
  );
}
