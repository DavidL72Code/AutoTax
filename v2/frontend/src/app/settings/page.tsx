"use client";

import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { Button, Card, Empty } from "@/components/ui";
import { API_BASE } from "@/lib/api";

function Row({ label, value, action }: { label: string; value: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-3 last:border-0">
      <div>
        <div className="text-[13px] text-ink">{label}</div>
        <div className="mt-0.5 text-[12px] text-ink-3">{value}</div>
      </div>
      {action}
    </div>
  );
}

export default function SettingsPage() {
  const { session, connectGmail, signOut, loading } = useApp();

  if (loading) {
    return (
      <Card>
        <Empty title="Loading…" />
      </Card>
    );
  }

  return (
    <>
      <PageHeader title="Settings" />

      <Card title="Account" className="mb-3">
        <Row
          label="Gmail"
          value={
            session?.gmail_connected
              ? `Connected as ${session.email}`
              : "Not connected — read-only access, revocable from your Google account"
          }
          action={
            session?.gmail_connected ? (
              <Button onClick={signOut}>Sign out</Button>
            ) : (
              <Button variant="primary" onClick={connectGmail}>
                Connect
              </Button>
            )
          }
        />
        <Row
          label="Parsing model"
          value={
            session?.model_configured
              ? "Gemini configured — used only for fields the rules cannot prove"
              : "No API key set. Rules-only parsing still resolves vendors, but misses awkward totals."
          }
        />
        <Row label="API" value={API_BASE} />
      </Card>

      <Card title="How your data is handled">
        <div className="space-y-2 px-4 py-4 text-[13px] leading-[1.55] text-ink-2">
          <p>Gmail access is read-only. Nothing is sent, labelled, or deleted in your mailbox.</p>
          <p>
            The refresh token is encrypted with your server&apos;s Fernet key before it is written to
            disk, and removing it here deletes it.
          </p>
          <p>
            Email bodies are not stored. Only the extracted fields, the parse trace, and the Gmail
            message id are kept — the id is what stops the next sync re-parsing the same receipt.
          </p>
          <p>
            When a field needs the model, only the financially relevant lines are sent, not the whole
            email.
          </p>
        </div>
      </Card>
    </>
  );
}
