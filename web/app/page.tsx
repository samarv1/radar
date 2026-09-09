import type { Metadata } from "next";
import { getFeed, getHiringFeed } from "@/lib/db";
import { FeedClient } from "@/components/FeedClient";

export const revalidate = 3600;

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default async function Home() {
  const [companies, hiringCompanies] = await Promise.all([
    getFeed(),
    getHiringFeed(),
  ]);

  return (
    <main className="w-full px-[12vw] py-8">
      <FeedClient companies={companies} hiringCompanies={hiringCompanies} />
    </main>
  );
}
