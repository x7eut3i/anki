"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import Sidebar from "@/components/sidebar";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { token } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (!token) {
      router.replace("/login");
    }
  }, [token, router]);

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
