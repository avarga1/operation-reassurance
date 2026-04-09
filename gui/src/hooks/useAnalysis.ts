import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useRepoPath } from "@/components/RepoSelector";

export function useAnalysis() {
  const path = useRepoPath();
  return useQuery({
    queryKey: ["analysis", path],
    queryFn: () => api.analyze(path),
    enabled: !!path,
  });
}

export function useBlastRadius(base = "main") {
  const path = useRepoPath();
  return useQuery({
    queryKey: ["blast-radius", path, base],
    queryFn: () => api.blastRadius(path, base),
    enabled: !!path,
  });
}

export function useConfig() {
  const path = useRepoPath();
  return useQuery({
    queryKey: ["config", path],
    queryFn: () => api.getConfig(path),
    enabled: !!path,
  });
}
