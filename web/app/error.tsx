"use client";

import Link from "next/link";

export default function Error({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="w-full px-[12vw] py-16 text-center">
      <h1 className="text-xl font-bold mb-2">Something went wrong</h1>
      <p className="text-sm text-muted-foreground mb-6">
        The feed couldn&apos;t load. Try again in a moment.
      </p>
      <div className="flex justify-center gap-4">
        <button
          onClick={() => reset()}
          className="text-sm underline hover:opacity-70 transition-opacity"
        >
          Try again
        </button>
        <Link href="/" className="text-sm underline hover:opacity-70 transition-opacity">
          Back home
        </Link>
      </div>
    </main>
  );
}
