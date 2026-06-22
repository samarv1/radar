import { Radar } from "lucide-react";
import { getFeed, getLastUpdated } from "@/lib/db";
import { FeedClient } from "@/components/FeedClient";

export const dynamic = "force-dynamic";

function lastUpdatedLabel(date: Date): string {
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export default async function Home() {
  const [companies, lastUpdated] = await Promise.all([getFeed(), getLastUpdated()]);

  return (
    <main className="w-full px-[12vw] py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Radar className="text-red-500" size={26} />
          Radar
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          hot & recently funded startups · updates daily · latest filing{" "}
          {lastUpdated ? lastUpdatedLabel(lastUpdated) : "—"}
        </p>
      </div>
      <FeedClient companies={companies} />
    </main>
  );
}
