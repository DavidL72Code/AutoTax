import { redirect } from "next/navigation";

/* The live run moved onto the dashboard, where it belongs — it was the thing
   the app actually does, filed under "System". Kept as a redirect so any
   bookmark still lands somewhere sensible. */
export default function ActivityPage() {
  redirect("/");
}
