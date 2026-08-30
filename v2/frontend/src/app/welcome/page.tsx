import { redirect } from "next/navigation";

/* Briefly the only way back to the landing, before "/" became the home page
   again. Kept so the link still works. */
export default function WelcomePage() {
  redirect("/");
}
