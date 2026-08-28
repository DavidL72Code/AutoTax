"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { API_BASE, api, NotificationFeed, RunState, Session, Stats, Transaction } from "@/lib/api";

type RunEvent = RunState & { type: "state" | "record" | "done"; record?: Transaction };

type Ctx = {
  session: Session | null;
  stats: Stats | null;
  transactions: Transaction[];
  run: RunState | null;
  liveRecords: Transaction[];
  notifications: NotificationFeed | null;
  unreadNotifications: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  refreshNotifications: () => Promise<void>;
  markNotificationsRead: (body: { ids?: string[]; all?: boolean }) => Promise<void>;
  startSync: () => Promise<void>;
  startDemo: () => Promise<void>;
  stopSync: () => Promise<void>;
  connectGmail: () => Promise<void>;
  signOut: () => Promise<void>;
  patch: (id: string, changes: Partial<Transaction>) => Promise<void>;
  remove: (id: string) => Promise<void>;
};

const AppContext = createContext<Ctx | null>(null);

export function AppState({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [liveRecords, setLiveRecords] = useState<Transaction[]>([]);
  const [notifications, setNotifications] = useState<NotificationFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.session();
      setSession(next);
      if (!next.signed_in) {
        setStats(null);
        setTransactions([]);
        setNotifications(null);
        return;
      }
      const [nextStats, nextTransactions] = await Promise.all([api.stats(), api.transactions()]);
      setStats(nextStats);
      setTransactions(nextTransactions.transactions);
      setError(null);
      // The bell should never be the reason a page fails to load, so this is
      // deliberately outside the awaited set.
      api.notifications().then(setNotifications).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const follow = useCallback(
    (state: RunState) => {
      setRun(state);
      setLiveRecords([]);
      streamRef.current?.close();

      const stream = new EventSource(`${API_BASE}/api/sync/${state.run_id}/events`, {
        withCredentials: true,
      });
      streamRef.current = stream;

      stream.onmessage = (event) => {
        const payload = JSON.parse(event.data) as RunEvent;
        setRun((current) => ({ ...(current ?? state), ...payload }));
        if (payload.type === "record" && payload.record) {
          setLiveRecords((current) => [payload.record as Transaction, ...current]);
        }
        if (payload.type === "done") {
          stream.close();
          streamRef.current = null;
          void refresh();
        }
      };
      stream.onerror = () => {
        stream.close();
        streamRef.current = null;
      };
    },
    [refresh],
  );

  useEffect(() => () => streamRef.current?.close(), []);

  const startSync = useCallback(async () => {
    setError(null);
    try {
      follow(await api.startSync({ max_results: 50, days_back: 180 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed to start");
    }
  }, [follow]);

  const startDemo = useCallback(async () => {
    setError(null);
    try {
      const state = await api.startDemo();
      await refresh();
      follow(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo failed to start");
    }
  }, [follow, refresh]);

  const stopSync = useCallback(async () => {
    if (run) await api.stopSync(run.run_id).catch(() => undefined);
  }, [run]);

  const connectGmail = useCallback(async () => {
    const { url } = await api.authUrl();
    window.location.href = url;
  }, []);

  const signOut = useCallback(async () => {
    await api.signOut();
    await refresh();
  }, [refresh]);

  const patch = useCallback(async (id: string, changes: Partial<Transaction>) => {
    const updated = await api.updateTransaction(id, changes);
    setTransactions((current) => current.map((row) => (row.id === id ? { ...row, ...updated } : row)));
    api.stats().then(setStats).catch(() => undefined);
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteTransaction(id);
    setTransactions((current) => current.filter((row) => row.id !== id));
    api.stats().then(setStats).catch(() => undefined);
  }, []);

  const refreshNotifications = useCallback(async () => {
    try {
      setNotifications(await api.notifications());
    } catch {
      // A failed poll leaves the last feed in place rather than blanking it.
    }
  }, []);

  const markNotificationsRead = useCallback(async (body: { ids?: string[]; all?: boolean }) => {
    setNotifications(await api.markRead(body));
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      session,
      stats,
      transactions,
      run,
      liveRecords,
      notifications,
      unreadNotifications: notifications?.unread ?? 0,
      loading,
      error,
      refresh,
      refreshNotifications,
      markNotificationsRead,
      startSync,
      startDemo,
      stopSync,
      connectGmail,
      signOut,
      patch,
      remove,
    }),
    [session, stats, transactions, run, liveRecords, notifications, loading, error, refresh, refreshNotifications, markNotificationsRead, startSync, startDemo, stopSync, connectGmail, signOut, patch, remove],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppState>");
  return ctx;
}
