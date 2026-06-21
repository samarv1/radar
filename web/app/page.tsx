import { getFeed } from "@/lib/db";
import { FeedClient } from "@/components/FeedClient";

export const dynamic = "force-dynamic";

export default async function Home() {
  const companies = await getFeed();
  const latest = companies.reduce((a, c) => (c.date_filed > a ? c.date_filed : a), "");

  return (
    <main className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Startup Feed</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {companies.length} recently funded companies · last filing{" "}
          {latest
            ? new Date(latest).toLocaleDateString("en-US", { month: "short", day: "numeric" })
            : "—"}
        </p>
      </div>
      <FeedClient companies={companies} />
    </main>
  );
}
