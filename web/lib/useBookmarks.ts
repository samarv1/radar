"use client";

// TODO (SSO): Replace localStorage with an API-backed implementation
// (/api/bookmarks GET/POST/DELETE) keyed by user session once SSO is introduced.

import { useState, useCallback } from "react";

const STORAGE_KEY = "radar_bookmarks";

function readFromStorage(): Set<number> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as number[]);
  } catch {
    return new Set();
  }
}

export function useBookmarks() {
  const [bookmarked, setBookmarked] = useState<Set<number>>(() => {
    if (typeof window === "undefined") return new Set();
    return readFromStorage();
  });

  const toggle = useCallback((id: number) => {
    setBookmarked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }, []);

  const isBookmarked = useCallback((id: number) => bookmarked.has(id), [bookmarked]);

  return { toggle, isBookmarked };
}
