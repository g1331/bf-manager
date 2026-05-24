"use client";

import { useQuery } from "@tanstack/react-query";
import { getSession, type SessionUser } from "@/lib/auth";

export function useSession() {
  return useQuery<SessionUser | null>({
    queryKey: ["session"],
    queryFn: getSession,
    staleTime: 60 * 1000,
  });
}
