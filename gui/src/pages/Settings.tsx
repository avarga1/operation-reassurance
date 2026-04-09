import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useConfig } from "@/hooks/useAnalysis";
import { useRepoPath } from "@/components/RepoSelector";
import { api } from "@/api/client";

export function Settings() {
  const path = useRepoPath();
  const { data, isLoading } = useConfig();
  const queryClient = useQueryClient();

  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const initialized = Object.keys(thresholds).length > 0;

  if (data && !initialized) {
    setThresholds({
      god_file_loc: data.config.thresholds?.god_file_loc ?? 500,
      god_file_functions: data.config.thresholds?.god_file_functions ?? 20,
      god_file_classes: data.config.thresholds?.god_file_classes ?? 5,
      god_class_methods: data.config.thresholds?.god_class_methods ?? 15,
      blast_radius_depth: data.config.thresholds?.blast_radius_depth ?? 2,
    });
  }

  const save = useMutation({
    mutationFn: () =>
      api.putConfig(path, {
        thresholds: thresholds as Record<string, number>,
        ignore: data?.config.ignore ?? [],
        analyzers: data?.config.analyzers ?? {},
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config", path] });
      queryClient.invalidateQueries({ queryKey: ["analysis", path] });
    },
  });

  if (!path) return <Empty />;
  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading config…</div>;

  const fields: { key: string; label: string; description: string }[] = [
    { key: "god_file_loc", label: "God file LOC", description: "Lines of code threshold per file" },
    { key: "god_file_functions", label: "God file functions", description: "Max functions/methods per file" },
    { key: "god_file_classes", label: "God file classes", description: "Max classes per file" },
    { key: "god_class_methods", label: "God class methods", description: "Max methods per class" },
    { key: "blast_radius_depth", label: "Blast radius depth", description: "Transitive caller depth" },
  ];

  return (
    <div className="p-6 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-lg font-bold">Settings</h1>
        <p className="text-xs text-muted-foreground mt-0.5 font-mono">
          {path}/.reassure.toml {data?.exists ? "" : "(will be created)"}
        </p>
      </div>

      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Thresholds
      </h2>
      <div className="border border-border divide-y divide-border mb-6">
        {fields.map(({ key, label, description }) => (
          <div key={key} className="flex items-center justify-between px-4 py-3">
            <div>
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-muted-foreground">{description}</div>
            </div>
            <input
              type="number"
              className="w-20 text-sm font-mono bg-background border border-border px-2 py-1 text-right outline-none focus:ring-1 focus:ring-ring"
              value={thresholds[key] ?? ""}
              onChange={(e) =>
                setThresholds((prev) => ({ ...prev, [key]: Number(e.target.value) }))
              }
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          className="text-sm border border-border px-4 py-2 hover:bg-accent/50 transition-colors disabled:opacity-50"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          {save.isPending ? "Saving…" : "Save to .reassure.toml"}
        </button>
        {save.isSuccess && (
          <span className="text-xs text-green-600">Saved. Re-run analysis to apply.</span>
        )}
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
      Select a repo to configure.
    </div>
  );
}
