"use client";

import { Landing } from "@/components/Landing";

/* The home page, always — the shape v1 had, where `index.html` explained the
   app and `console.html` was the ledger. v2 had these inverted: "/" was the
   dashboard and the landing only appeared when there was no data, so it
   disappeared the moment a demo ran. */
export default function HomePage() {
  return <Landing />;
}
