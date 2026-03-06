"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import Sidebar from "@/components/sidebar";
import { Loader2 } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { token } = useAuthStore();
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  // Wait for Zustand persist to finish hydrating from localStorage
  useEffect(() => {
    // If already hydrated (e.g. SPA navigation), set immediately
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    // Otherwise wait for rehydration to complete
    const unsub = useAuthStore.persist.onFinishHydration(() => {
      setHydrated(true);
    });
    return unsub;
  }, []);

  // Only redirect to login after hydration confirms no token
  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  // Show loading spinner while hydrating
  if (!hydrated) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!token) return null;

  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="md:pl-64 pb-20 md:pb-0">
        <div className="container mx-auto px-4 py-6 max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
