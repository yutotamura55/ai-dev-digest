import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { DigestView } from "@/components/DigestView";
import { fetchDigest, isValidDate } from "@/digest/articles";

export default function DayPage({ params }: PageProps<"/days/[date]">) {
  return (
    <main>
      <h1>ai-dev-digest</h1>
      <Suspense fallback={<p>読み込み中…</p>}>
        {params.then(({ date }) => (
          <DayDigest date={date} />
        ))}
      </Suspense>
    </main>
  );
}

async function DayDigest({ date }: { date: string }) {
  if (!isValidDate(date)) {
    notFound();
  }
  await connection();
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const digest = await fetchDigest(apiBaseUrl, date);
  return <DigestView digest={digest} isToday={false} />;
}
