"use client";
import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api, ApiError, getOrgId } from "./api";
import { toast } from "@/components/ui/toast";

export function useApiQuery<T = any>(path: string | null, opts: Partial<UseQueryOptions<T>> = {}) {
  const org = typeof window !== "undefined" ? getOrgId() : null;
  return useQuery<T>({
    queryKey: [org, path],
    queryFn: () => api<T>(path!),
    enabled: !!path && (opts.enabled ?? true),
    ...opts,
  });
}

export function useApiMutation<TBody = any, TRes = any>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string | ((b: TBody) => string),
  opts: { invalidate?: string[]; onSuccess?: (r: TRes, b: TBody) => void; errorTitle?: string } = {},
) {
  const qc = useQueryClient();
  return useMutation<TRes, ApiError, TBody>({
    mutationFn: (body: TBody) => api<TRes>(typeof path === "function" ? path(body) : path, { method, json: body ?? undefined }),
    onSuccess: (r, b) => {
      (opts.invalidate || []).forEach((p) => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[1] || "").startsWith(p) }));
      opts.onSuccess?.(r, b);
    },
    onError: (e) => toast(opts.errorTitle || "Error", e.message === "network" ? "Can't reach the Idrak server" : e.message, "error"),
  });
}
