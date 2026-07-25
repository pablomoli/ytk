import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type JobStatus = {
  running: boolean;
  total: number;
  done: number;
  current: string | null;
  current_started: number | null;
  queued: string[];
  failures: { url: string; error: string }[];
  annotated: number;
  linked: string[];
};

export const fetchJob = () => apiGet<JobStatus>("/api/ingest/status");

// Poll once per second only while a job is running; when idle, stop polling so
// the inbox does not re-render (and MasonryGrid does not relayout) every second.
// Add/refresh mutations invalidate ['job'] to kick a fresh poll when they may
// have started work.
//
// Keep polling through errors: the hub is killed and restarted under us whenever
// its package is reinstalled, and it resumes the batch on boot. Stopping on the
// first refused connection would strand the UI on a job that is still running.
// Poll in the background too — a batch runs ~2 minutes per video, longer than
// anyone watches the tab.
export const useJobStatus = () =>
  useQuery({
    queryKey: ["job"],
    queryFn: fetchJob,
    refetchInterval: (query) =>
      query.state.data?.running || query.state.status === "error" ? 1000 : false,
    refetchIntervalInBackground: true,
  });
