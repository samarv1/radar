import type { Metadata } from "next";
import Link from "next/link";
import { Radar } from "lucide-react";

export const metadata: Metadata = {
  title: "Philosophy — Radar",
  description: "How to think about startup recruiting: what signals to look for, when to reach out, how to outreach.",
};

export default function PhilosophyPage() {
  return (
    <main className="w-full px-[12vw] py-8">
      <div className="mb-6">
        <Link href="/" className="inline-block hover:opacity-70 transition-opacity">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Radar className="text-red-500" size={26} />
            Radar
          </h1>
        </Link>
        <p className="text-sm text-muted-foreground mt-1">
          how to turn this data into quality job leads
        </p>
      </div>
      <div className="text-sm leading-relaxed space-y-6 max-w-3xl">
        <section>
          <h2 className="font-semibold mb-2">timing</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>recency after early startup funding is vital: fresh money, the startup is small enough to consider random inbound, and aggressive recruiting hasn&apos;t necessarily begun</li>
            <li>series a averages ~54 days to first hire, series b ~26 days, series c ~20 days after funding (signalbase)</li>
          </ul>
        </section>
        <section>
          <h2 className="font-semibold mb-2">signals</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>no posted role does not mean &quot;not hiring&quot;: if they have money and you can <strong className="font-semibold">position yourself to their needs</strong>, you can look hireable</li>
          </ul>
        </section>
        <section>
          <h2 className="font-semibold mb-2">outreach</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>cold email if you can offer something specific: you should either be connected to them somehow or provide value in some way</li>
            <li>
              who to message
              <ul className="list-[circle] pl-5 mt-1 space-y-1">
                <li>closest connection at the company or most relevant person to hire for your role</li>
                <li>founder can work at companies sub-50 employees</li>
              </ul>
            </li>
            <li><strong className="font-semibold">you are what you describe yourself as</strong>: frame your background in terms of what you can directly help with, not just your resume points</li>
            <li>personalize to their product, stack, or problem space</li>
            <li><strong className="font-semibold">3-5 touches</strong> is optimal range for reply rate before returns drop off</li>
            <li>
              tools
              <ul className="list-[circle] pl-5 mt-1 space-y-1">
                <li><strong className="font-semibold">apollo</strong>: find emails on linkedin accounts</li>
                <li><strong className="font-semibold">heyreach.io</strong>: automate and scale linkedin outreach</li>
              </ul>
            </li>
          </ul>
        </section>
      </div>
    </main>
  );
}
