import { useState, useEffect } from "react";
import { api } from "@/api/client";

const KEY_STORAGE = "reassure:kai_key";
const URL_STORAGE = "reassure:kai_studio_url";

export interface KaiAuthState {
  key: string;
  studioUrl: string | null;
  status: "idle" | "verifying" | "valid" | "invalid" | "unconfigured";
  verify: (key: string) => Promise<void>;
  clear: () => void;
}

export function useKaiAuth(): KaiAuthState {
  const [key, setKey] = useState(() => localStorage.getItem(KEY_STORAGE) ?? "");
  const [studioUrl, setStudioUrl] = useState<string | null>(
    () => localStorage.getItem(URL_STORAGE)
  );
  const [status, setStatus] = useState<KaiAuthState["status"]>(
    () => (localStorage.getItem(KEY_STORAGE) ? "idle" : "idle")
  );

  // On mount: if we have a saved key, re-verify it silently
  useEffect(() => {
    const saved = localStorage.getItem(KEY_STORAGE);
    if (!saved) return;
    setStatus("verifying");
    api.verifyKaiKey(saved)
      .then((res) => {
        setStudioUrl(res.studio_url);
        localStorage.setItem(URL_STORAGE, res.studio_url);
        setStatus("valid");
      })
      .catch((err: Error) => {
        if (err.message.includes("not configured")) {
          setStatus("unconfigured");
        } else {
          setStatus("invalid");
        }
      });
  }, []);

  async function verify(candidate: string) {
    setStatus("verifying");
    try {
      const res = await api.verifyKaiKey(candidate);
      setKey(candidate);
      setStudioUrl(res.studio_url);
      localStorage.setItem(KEY_STORAGE, candidate);
      localStorage.setItem(URL_STORAGE, res.studio_url);
      setStatus("valid");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      setStatus(msg.includes("not configured") ? "unconfigured" : "invalid");
    }
  }

  function clear() {
    localStorage.removeItem(KEY_STORAGE);
    localStorage.removeItem(URL_STORAGE);
    setKey("");
    setStudioUrl(null);
    setStatus("idle");
  }

  return { key, studioUrl, status, verify, clear };
}
