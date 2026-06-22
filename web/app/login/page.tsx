"use client";

// TODO (SSO): Remove this page once SSO is introduced.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Radar } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });

    if (res.ok) {
      router.push("/");
      router.refresh();
    } else {
      setError("Incorrect password.");
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Radar className="text-red-500" size={26} />
            Radar
          </h1>
          <p className="text-sm text-muted-foreground">Enter the password to continue.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            required
            className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-foreground text-background rounded-md px-3 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Checking…" : "Enter"}
          </button>
        </form>
      </div>
    </main>
  );
}
