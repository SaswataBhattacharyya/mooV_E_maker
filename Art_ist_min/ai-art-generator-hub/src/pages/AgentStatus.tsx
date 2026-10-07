import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Home,
  Image as ImageIcon,
  Loader2,
  Server,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CURRENT_PROJECT_KEY,
  fetchProjectStatus,
  getProjectFileUrl,
  getSupervisorUrl,
  type ProjectRuntimeStatus,
} from "@/lib/project-api";

const POLL_INTERVAL = 2000;

const AgentStatus = () => {
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState<string | null>(null);

  useEffect(() => {
    setProjectId(localStorage.getItem(CURRENT_PROJECT_KEY));
  }, []);

  const { data: status, isLoading, error } = useQuery({
    queryKey: ["project-status", projectId],
    queryFn: () => fetchProjectStatus(projectId!),
    enabled: Boolean(projectId),
    refetchInterval: POLL_INTERVAL,
  });

  const acceptedImages = useMemo(() => status?.accepted_images ?? [], [status]);

  const getLogIcon = (level: string) => {
    switch (level) {
      case "success":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "error":
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-500" />;
      default:
        return <Activity className="h-4 w-4 text-primary" />;
    }
  };

  const dependencyBadge = (ok: boolean) => (
    <Badge variant={ok ? "default" : "destructive"}>{ok ? "Online" : "Offline"}</Badge>
  );

  const runtimeState = status?.runtime.state || "IDLE";
  const supervisor = status?.supervisor;
  const actionableDiagnosis = supervisor?.actionable_diagnosis;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <Sparkles className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-semibold tracking-tight text-foreground">Project Status & Logs</h1>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={getSupervisorUrl(projectId)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium ring-offset-background transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              Supervisor
            </a>
            <Button variant="outline" onClick={() => navigate("/")} className="flex items-center gap-2">
              <Home className="h-4 w-4" />
              Home
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-10">
        {!projectId ? (
          <Card>
            <CardHeader>
              <CardTitle>No Active Project</CardTitle>
              <CardDescription>Save a draft on the home page first.</CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Current Status</CardTitle>
                      <CardDescription>{status?.title || projectId}</CardDescription>
                    </div>
                    {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {error ? (
                    <p className="text-sm text-destructive">Failed to load project status.</p>
                  ) : status ? (
                    <>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={runtimeState === "FAILED" ? "destructive" : "secondary"}>{runtimeState}</Badge>
                        <Badge variant="outline">{status.current_stage}</Badge>
                        <Badge variant="outline">{status.status}</Badge>
                        {supervisor?.mode ? <Badge variant="outline">Ripa: {supervisor.mode}</Badge> : null}
                        {supervisor?.waiting_for_user ? <Badge variant="destructive">Waiting for you</Badge> : null}
                      </div>
                      <p className="text-sm text-muted-foreground">{status.runtime.current_task}</p>
                      {supervisor?.current_review ? (
                        <p className="text-xs text-muted-foreground">Current review: {supervisor.current_review}</p>
                      ) : null}
                      {status.runtime.progress > 0 ? (
                        <div className="h-2 w-full rounded-full bg-secondary">
                          <div
                            className="h-2 rounded-full bg-primary transition-all"
                            style={{ width: `${status.runtime.progress}%` }}
                          />
                        </div>
                      ) : null}
                      {status.runtime.last_error ? (
                        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                          {status.runtime.last_error}
                        </div>
                      ) : null}
                      {actionableDiagnosis ? (
                        <div className="rounded-lg border border-border bg-card p-3 text-sm">
                          <p className="font-medium text-foreground">Ripa Diagnosis</p>
                          <p className="text-muted-foreground">Layer: {actionableDiagnosis.layer}</p>
                          <p className="text-muted-foreground">Stage: {actionableDiagnosis.stage}</p>
                          <p className="text-foreground">{actionableDiagnosis.reason}</p>
                          <p className="text-muted-foreground">Next: {actionableDiagnosis.next_action}</p>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">Loading status...</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Live Runtime Log</CardTitle>
                  <CardDescription>Project-scoped backend and generation activity.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {status?.logs?.length ? (
                    status.logs
                      .slice()
                      .reverse()
                      .map((log) => (
                        <div key={log.id} className="flex items-start gap-3 rounded-lg border border-border bg-card p-3">
                          {getLogIcon(log.level)}
                          <div className="flex-1 space-y-1">
                            <p className="text-sm text-foreground">{log.message}</p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(log.timestamp).toLocaleTimeString()}
                            </p>
                          </div>
                        </div>
                      ))
                  ) : (
                    <p className="py-8 text-center text-sm text-muted-foreground">No logs yet</p>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-primary" />
                    <CardTitle>Dependencies</CardTitle>
                  </div>
                  <CardDescription>Service health for the current project pipeline.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground">Ollama</span>
                    {dependencyBadge(Boolean(status?.dependencies.ollama))}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-foreground">ComfyUI</span>
                    {dependencyBadge(Boolean(status?.dependencies.comfyui))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Completed Work</CardTitle>
                  <CardDescription>Finished runtime steps for this project.</CardDescription>
                </CardHeader>
                <CardContent>
                  {status?.runtime.completed_tasks?.length ? (
                    <ul className="space-y-2">
                      {status.runtime.completed_tasks.map((task, index) => (
                        <li key={`${task}-${index}`} className="flex items-center gap-2 text-sm">
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
                          <span>{task}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No completed tasks yet.</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Accepted Images</CardTitle>
                  <CardDescription>Outputs approved so far for this project.</CardDescription>
                </CardHeader>
                <CardContent>
                  {acceptedImages.length ? (
                    <div className="grid gap-4">
                      {acceptedImages.map((artifact) => (
                        <div key={artifact.candidate_id} className="space-y-3 rounded-lg border border-border bg-card p-3">
                          <div className="flex items-center gap-2">
                            <ImageIcon className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium text-foreground">{artifact.job_id}</span>
                          </div>
                          <img
                            src={getProjectFileUrl(projectId, artifact.relative_path)}
                            alt={artifact.job_id}
                            className="w-full rounded-lg border border-border"
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No accepted images yet.</p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default AgentStatus;
