import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { AudioLines, Film, FolderCog, LayoutDashboard, Library, Loader2, Mic2, Music2, PenTool, ScrollText, Sparkles, Workflow, ScanSearch, WandSparkles } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { actionStoryAutomation, getReasoningProvider, listAutomationProjects, setReasoningProvider, testReasoningDirector, testReasoningProvider, type AutomationRunState, type ReasoningProviderCatalog, type ReasoningProviderOption } from "@/lib/project-api";
import { Button } from "@/components/ui/button";

const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/story", label: "Story Builder", icon: PenTool },
  { to: "/canvas", label: "Story Canvas", icon: ScrollText },
  { to: "/media", label: "Media Composer", icon: Film },
  { to: "/generate", label: "Generate", icon: Sparkles },
  { to: "/video-repertoire", label: "Video Repertoire", icon: Library },
  { to: "/video-summariser", label: "Video Summariser", icon: Library },
  { to: "/manual-director", label: "Manual Director", icon: WandSparkles },
  { to: "/production", label: "Production V2", icon: Film },
  { to: "/style-library", label: "Style Library", icon: Library },
  { to: "/image-detailer", label: "Image Detailer", icon: ScanSearch },
  { to: "/audio", label: "Audio Studio", icon: AudioLines },
  { to: "/audio-reconstruct", label: "Audio Reconstruct", icon: Mic2 },
  { to: "/music-sound", label: "Music & Sound", icon: Music2 },
  { to: "/audio-tools", label: "Audio Utilities", icon: FolderCog },
  { to: "/automation", label: "Automation", icon: Workflow },
  { to: "/status", label: "Status", icon: Sparkles },
];

const providerOptionsFallback: ReasoningProviderOption[] = [
  { id: "ollama", label: "Ollama (current)", model: "Current model", available: false, compatibility: true },
  { id: "codex", label: "Codex · gpt-6-luna", model: "gpt-6-luna", available: false, compatibility: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<AutomationRunState | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [providerCatalog, setProviderCatalog] = useState<ReasoningProviderCatalog | null>(null);
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerTestBusy, setProviderTestBusy] = useState(false);
  useEffect(() => {
    const refresh = () => listAutomationProjects().then((projects) => {
      const candidate = projects.map((item) => item.automation_run).find((value) => value && ["queued", "running", "paused"].includes(value.status)) || projects.map((item) => item.automation_run).find(Boolean) || null;
      setRun(candidate as AutomationRunState | null);
    }).catch(() => undefined);
    refresh();
    const timer = window.setInterval(refresh, 1600);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { getReasoningProvider().then(setProviderCatalog).catch(() => undefined); }, []);
  useEffect(() => {
    if (!run || !["queued", "running", "paused"].includes(run.status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);
  const active = run && ["queued", "running", "paused"].includes(run.status);
  const monitorOpen = Boolean(run) && !collapsed;
  const elapsed = run?.started_at ? Math.max(0, Math.floor((now - Date.parse(run.started_at)) / 1000)) : 0;
  const elapsedLabel = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}m ${String(elapsed % 60).padStart(2, "0")}s`;
  const selectedProvider = providerCatalog?.providers.find((item) => item.id === providerCatalog.provider);
  const changeProvider = async (provider: ReasoningProviderOption["id"]) => {
    setProviderBusy(true);
    try {
      setProviderCatalog(await setReasoningProvider(provider));
      toast.success(`New reasoning calls will use ${provider === "codex" ? "Codex · gpt-6-luna" : "Ollama"}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update reasoning provider");
    } finally { setProviderBusy(false); }
  };
  const runProviderTest = async () => {
    if (!providerCatalog) return;
    setProviderTestBusy(true);
    try {
      const result = await testReasoningProvider(providerCatalog.provider);
      toast.success(`${result.provider} returned valid JSON using ${result.model || "its configured model"} in ${(result.elapsed_ms / 1000).toFixed(1)}s.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Provider smoke test failed");
    } finally { setProviderTestBusy(false); }
  };
  const runDirectorTest = async () => {
    if (!providerCatalog) return;
    setProviderTestBusy(true);
    try {
      const result = await testReasoningDirector(providerCatalog.provider);
      toast.success(`${result.provider} director test passed: ${result.shot_count} shot(s), ${result.model || "configured model"}, ${(result.elapsed_ms / 1000).toFixed(1)}s.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Director test failed");
    } finally { setProviderTestBusy(false); }
  };
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link to="/" className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-primary">story_builder</p>
            <h1 className="text-2xl font-semibold tracking-tight">Story + Media Workspace</h1>
          </Link>
          <nav className="flex flex-wrap gap-2">
            {links.map((link) => {
              const Icon = link.icon;
              return (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors",
                      isActive ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
                    )
                  }
                >
                  <Icon className="h-4 w-4" />
                  {link.label}
                </NavLink>
              );
            })}
          </nav>
        </div>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-end gap-3 border-t border-border/70 px-6 py-2.5">
          <div className="mr-auto min-w-0">
            <p className="text-xs font-medium">Reasoning provider</p>
            <p className="text-[11px] text-muted-foreground">Applies to story and director steps; active runs keep their starting choice.</p>
          </div>
          {selectedProvider ? <span className="hidden text-xs text-muted-foreground sm:inline">{selectedProvider.model} · {selectedProvider.available ? "CLI present" : "CLI missing"}</span> : null}
          <select aria-label="Reasoning provider" className="h-9 max-w-[13rem] rounded-md border border-input bg-background px-2 text-xs" value={providerCatalog?.provider || "codex"} disabled={!providerCatalog || providerBusy || providerTestBusy} onChange={(event) => changeProvider(event.target.value as ReasoningProviderOption["id"])}>
            {(providerCatalog?.providers || providerOptionsFallback).map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
          <Button size="sm" variant="outline" className="h-9 px-3 text-xs" disabled={!providerCatalog || providerBusy || providerTestBusy} onClick={runProviderTest}>
            {providerTestBusy ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Testing…</> : "Test selected"}
          </Button>
          <Button size="sm" variant="outline" className="h-9 px-3 text-xs" aria-label="Test director with selected provider" disabled={!providerCatalog || providerBusy || providerTestBusy} onClick={runDirectorTest}>
            {providerTestBusy ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Testing…</> : "Test director"}
          </Button>
        </div>
      </header>
      <main className={cn("mx-auto max-w-7xl px-6 py-8", monitorOpen && "pb-36")}>{children}</main>
      {run ? <div className={cn("fixed inset-x-0 bottom-0 z-50 border-t border-primary/25 bg-background/95 shadow-2xl backdrop-blur", collapsed ? "px-4 py-2" : "px-4 py-3")}><div className="mx-auto max-w-7xl"><div className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><span className={cn("h-2.5 w-2.5 rounded-full", run.status === "failed" ? "bg-destructive" : run.status === "paused" ? "bg-yellow-500" : "animate-pulse bg-primary")} /><p className="truncate text-sm font-medium">Automation · {run.current_stage} · {run.status}</p><span className="text-xs text-muted-foreground">{run.progress}%</span><span className="text-xs tabular-nums text-muted-foreground">{run.status === "completed" ? "done" : elapsedLabel}</span></div><div className="flex items-center gap-2"><button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setCollapsed((value) => !value)}>{collapsed ? "Expand" : "Minimize"}</button>{run.status === "running" ? <button className="rounded-md border px-2 py-1 text-xs" onClick={() => actionStoryAutomation(run.project_id, "pause").then(setRun)}>Pause</button> : null}{run.status === "paused" ? <button className="rounded-md border px-2 py-1 text-xs" onClick={() => actionStoryAutomation(run.project_id, "resume").then(setRun)}>Resume</button> : null}</div></div>{!collapsed ? <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all duration-500" style={{ width: `${run.progress}%` }} /></div> : null}</div></div> : null}
    </div>
  );
}
