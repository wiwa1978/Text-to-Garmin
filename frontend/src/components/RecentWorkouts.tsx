import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, RefreshCw, Trash2 } from "lucide-react";

import { api, type WorkoutSummary } from "../api";
import { loadCreds, type StoredCreds } from "./CredentialsModal";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

interface Props {
  /** Changes to this key trigger a refresh (e.g. increment after a successful upload). */
  refreshKey?: number;
  /** Called when the backend says auth_required; parent opens the credentials modal. */
  onAuthRequired: (retry: (creds: StoredCreds) => Promise<void>) => void;
}

function formatDuration(secs?: number | null): string | null {
  if (!secs) return null;
  const m = Math.round(secs / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

function formatDistance(m?: number | null): string | null {
  if (!m) return null;
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m)} m`;
}

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function RecentWorkouts({ refreshKey = 0, onAuthRequired }: Props) {
  const [open, setOpen] = useState(true);
  const [workouts, setWorkouts] = useState<WorkoutSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<WorkoutSummary | null>(
    null
  );
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(
    async (creds?: StoredCreds) => {
      setLoading(true);
      setError(null);
      try {
        const resp = await api.listRecentWorkouts({
          limit: 20,
          email: creds?.email,
          password: creds?.password,
        });
        if (resp.status === "ok") {
          setWorkouts(resp.workouts);
          setLoadedOnce(true);
          return;
        }
        if (resp.status === "auth_required") {
          onAuthRequired(async (c) => {
            await load(c);
          });
          return;
        }
        setError(resp.error || "Failed to load workouts.");
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [onAuthRequired]
  );

  // Load when the panel is first opened and whenever refreshKey changes.
  useEffect(() => {
    if (!open) return;
    void load(loadCreds() ?? undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, refreshKey]);

  async function runDelete(creds?: StoredCreds) {
    if (!confirmDelete?.workout_id) return;
    setDeleting(true);
    setError(null);
    try {
      const resp = await api.deleteGarminWorkout(confirmDelete.workout_id, {
        email: creds?.email,
        password: creds?.password,
      });
      if (resp.status === "ok") {
        setWorkouts((prev) =>
          prev.filter((w) => w.workout_id !== confirmDelete.workout_id)
        );
        setConfirmDelete(null);
        return;
      }
      if (resp.status === "auth_required") {
        onAuthRequired(async (c) => {
          await runDelete(c);
        });
        return;
      }
      setError(resp.error || "Delete failed.");
    } catch (e) {
      setError(String(e));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Card>
        <CardHeader
          className="flex cursor-pointer flex-row items-center justify-between gap-2 space-y-0 py-3"
          onClick={() => setOpen((v) => !v)}
        >
          <CardTitle className="flex items-center gap-2 text-base font-medium">
            {open ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
            Recent workouts
            {loadedOnce && !loading && (
              <span className="text-xs font-normal text-muted-foreground">
                ({workouts.length})
              </span>
            )}
          </CardTitle>
          {open && (
            <Button
              variant="ghost"
              size="sm"
              disabled={loading}
              onClick={(e) => {
                e.stopPropagation();
                void load(loadCreds() ?? undefined);
              }}
            >
              <RefreshCw
                className={`size-4 ${loading ? "animate-spin" : ""}`}
              />
            </Button>
          )}
        </CardHeader>
        {open && (
          <CardContent className="pt-0">
            {error && (
              <p className="mb-2 text-sm text-destructive">{error}</p>
            )}
            {loading && !loadedOnce && (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
            {loadedOnce && workouts.length === 0 && !loading && (
              <p className="text-sm text-muted-foreground">
                No workouts found on your Garmin Connect account yet.
              </p>
            )}
            {workouts.length > 0 && (
              <ul className="divide-y divide-border">
                {workouts.map((w) => {
                  const duration = formatDuration(w.estimated_duration_s);
                  const distance = formatDistance(w.estimated_distance_m);
                  const updated = formatDate(w.updated_date ?? w.created_date);
                  const meta = [w.sport_type, duration, distance, updated]
                    .filter(Boolean)
                    .join(" · ");
                  const href =
                    w.workout_id != null
                      ? `https://connect.garmin.com/modern/workout/${w.workout_id}`
                      : undefined;
                  return (
                    <li
                      key={w.workout_id ?? w.name}
                      className="flex items-center justify-between gap-3 py-2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {w.name}
                        </div>
                        {meta && (
                          <div className="truncate text-xs text-muted-foreground">
                            {meta}
                          </div>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {href && (
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            title="Open on Garmin Connect"
                          >
                            <a href={href} target="_blank" rel="noreferrer">
                              <ExternalLink className="size-4" />
                            </a>
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Delete workout"
                          disabled={w.workout_id == null}
                          onClick={() => setConfirmDelete(w)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        )}
      </Card>

      <Dialog
        open={confirmDelete !== null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete workout?</DialogTitle>
            <DialogDescription>
              This removes <strong>{confirmDelete?.name}</strong> from your
              Garmin Connect account. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setConfirmDelete(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={() => runDelete(loadCreds() ?? undefined)}
            >
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
