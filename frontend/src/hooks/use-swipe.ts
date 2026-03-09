"use client";

import { useRef, useEffect, useCallback } from "react";

interface SwipeOptions {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold?: number; // minimum px distance for a swipe
}

/**
 * Hook to detect horizontal swipe gestures on a ref element.
 * Returns a ref to attach to the swipeable container.
 */
export function useSwipe<T extends HTMLElement = HTMLDivElement>({
  onSwipeLeft,
  onSwipeRight,
  threshold = 50,
}: SwipeOptions) {
  const ref = useRef<T>(null);
  const startX = useRef<number | null>(null);
  const startY = useRef<number | null>(null);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    startX.current = e.touches[0].clientX;
    startY.current = e.touches[0].clientY;
  }, []);

  const handleTouchEnd = useCallback(
    (e: TouchEvent) => {
      if (startX.current === null || startY.current === null) return;
      const dx = e.changedTouches[0].clientX - startX.current;
      const dy = e.changedTouches[0].clientY - startY.current;
      startX.current = null;
      startY.current = null;

      // Only trigger if horizontal distance exceeds vertical (avoid scroll conflicts)
      if (Math.abs(dx) < threshold || Math.abs(dx) < Math.abs(dy)) return;

      if (dx < 0) {
        onSwipeLeft?.();
      } else {
        onSwipeRight?.();
      }
    },
    [onSwipeLeft, onSwipeRight, threshold],
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchend", handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchEnd]);

  return ref;
}
