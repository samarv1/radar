import { getFeed, getLastUpdated } from "@/lib/db";
import { FeedClient } from "@/components/FeedClient";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [companies, lastUpdated] = await Promise.all([getFeed(), getLastUpdated()]);

  return (
    <main className="w-full px-[12vw] py-8">
      <FeedClient companies={companies} lastUpdated={lastUpdated} />
    </main>
  );
}
