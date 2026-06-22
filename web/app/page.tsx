import { getFeed, getLastUpdated } from "@/lib/db";
import { FeedClient } from "@/components/FeedClient";

export const dynamic = "force-dynamic";

function relativeDate(date: Date): string {
  const today = new Date();
  const diffMs = today.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  return `${diffDays} days ago`;
}

export default async function Home() {
  const [companies, lastUpdated] = await Promise.all([getFeed(), getLastUpdated()]);

  return (
    <main className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Startup Feed</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {companies.length} recently funded startups · updated{" "}
          {lastUpdated ? relativeDate(lastUpdated) : "—"}
        </p>
      </div>
      <FeedClient companies={companies} />
    </main>
  );
}
