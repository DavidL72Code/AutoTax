"use client";

import { Landing } from "@/components/Landing";

/* The same landing as a signed-out "/", but reachable at any time. Once a demo
   starts, "/" becomes the dashboard, so without this the page explaining what
   the app does could never be seen again without signing out. */
export default function WelcomePage() {
  return <Landing />;
}
