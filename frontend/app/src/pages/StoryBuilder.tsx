import { useEffect, useMemo, useState } from "react";
import { Lightbulb, Loader2, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { NEW_PRODUCTION_NAV_ENABLED, selectProductionProject } from "@/lib/production-navigation";
import { ProductionStylePicker } from "@/components/ProductionStylePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  createProject,
  CURRENT_PROJECT_KEY,
  fetchProject,
  generateArtifact,
  requestStoryAssist,
  saveArtifact,
  STORY_DRAFT_KEY,
  updateProjectDraft,
  listAutomationStyles,
  startStoryAutomation,
  startProduction,
  getProductionRun,
  getStoryAutomation,
  actionStoryAutomation,
  type AutomationStyle,
  type AutomationRunState,
  type ArtifactType,
  type ProjectState,
} from "@/lib/project-api";

const artifactOrder: ArtifactType[] = ["story", "characters", "scenes", "subscenes", "dialogue", "image_jobs"];
const artifactLabels: Record<ArtifactType, string> = {
  story: "Story Blueprint",
  characters: "Character Sheet",
  scenes: "Scene Plan",
  subscenes: "Sub-scene Plan",
  dialogue: "Dialogue Plan",
  image_jobs: "Image Queue",
};

export default function StoryBuilder() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [storyInput, setStoryInput] = useState("");
  const [automationMode, setAutomationMode] = useState(false);
  const [project, setProject] = useState<ProjectState | null>(null);
  const [artifactDrafts, setArtifactDrafts] = useState<Record<string, string>>({});
  const [artifactDirty, setArtifactDirty] = useState<Record<string, boolean>>({});
  const [assistFocus, setAssistFocus] = useState("refine");
  const [assist, setAssist] = useState<null | {
    summary: string;
    questions: string[];
    recommendations: string[];
    revised_text: string;
  }>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [styles, setStyles] = useState<AutomationStyle[]>([]);
  const [styleId, setStyleId] = useState("story_film");
  const [narrativeVariantId, setNarrativeVariantId] = useState("");
  const [detailStory, setDetailStory] = useState(true);
  const [automationRun, setAutomationRun] = useState<AutomationRunState | null>(null);
  const [productionRun, setProductionRun] = useState<{ status: string; stage?: string; progress?: number; error?: string | null } | null>(null);

  useEffect(() => {
    const savedDraft = localStorage.getItem(STORY_DRAFT_KEY);
    if (savedDraft) {
      try {
        const parsed = JSON.parse(savedDraft);
        setTitle(parsed.title || "");
        setStoryInput(parsed.storyInput || "");
        setAutomationMode(Boolean(parsed.automationMode));
      } catch {
        // ignore corrupt draft
      }
    }
    const savedProjectId = localStorage.getItem(CURRENT_PROJECT_KEY);
    listAutomationStyles().then((items) => { setStyles(items); if (items[0] && !items.some((item) => item.style_id === styleId)) setStyleId(items[0].style_id); }).catch(() => undefined);
    if (!savedProjectId) {
      return;
    }
    fetchProject(savedProjectId)
      .then((nextProject) => {
        hydrateProject(nextProject);
        setTitle(nextProject.title);
        setStoryInput(nextProject.story_input);
        setAutomationMode(nextProject.automation_mode);
        if (nextProject.automation_run) setAutomationRun(nextProject.automation_run);
        getProductionRun(nextProject.id).then((run) => { if (run.status !== "idle") setProductionRun(run); }).catch(() => undefined);
      })
      .catch(() => localStorage.removeItem(CURRENT_PROJECT_KEY));
  }, []);

  useEffect(() => {
    if (!project?.id || !automationRun || !["queued", "running", "paused"].includes(automationRun.status)) return;
    const timer = window.setInterval(() => getStoryAutomation(project.id).then(setAutomationRun).catch(() => undefined), 1400);
    return () => window.clearInterval(timer);
  }, [project?.id, automationRun?.status]);

  useEffect(() => {
    if (!project?.id || !productionRun || !["queued", "running", "retrying"].includes(productionRun.status)) return;
    const timer = window.setInterval(() => getProductionRun(project.id).then(setProductionRun).catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [project?.id, productionRun?.status]);

  useEffect(() => {
    localStorage.setItem(STORY_DRAFT_KEY, JSON.stringify({ title, storyInput, automationMode }));
  }, [title, storyInput, automationMode]);

  const hydrateProject = (nextProject: ProjectState, preserveDirty = false) => {
    setProject(nextProject);
    localStorage.setItem(CURRENT_PROJECT_KEY, nextProject.id);
    setArtifactDrafts((current) => {
      const nextDrafts = { ...current };
      for (const artifactType of artifactOrder) {
        if (preserveDirty && artifactDirty[artifactType]) {
          continue;
        }
        nextDrafts[artifactType] = nextProject.artifacts[artifactType].content
          ? JSON.stringify(nextProject.artifacts[artifactType].content, null, 2)
          : "";
      }
      return nextDrafts;
    });
  };

  const completedArtifacts = useMemo(
    () => artifactOrder.filter((artifactType) => project?.artifacts[artifactType].content).length,
    [project]
  );

  const withBusy = async (key: string, action: () => Promise<void>) => {
    setBusyKey(key);
    try {
      await action();
    } finally {
      setBusyKey(null);
    }
  };

  const saveProjectDraft = async () => {
    if (!title.trim() || !storyInput.trim()) {
      toast.error("Title and rough story are required.");
      return;
    }
    await withBusy("draft", async () => {
      const nextProject = project
        ? await updateProjectDraft({
            projectId: project.id,
            title: title.trim(),
            story_input: storyInput.trim(),
            automation_mode: automationMode,
          })
        : await createProject({
            title: title.trim(),
            story_input: storyInput.trim(),
            automation_mode: automationMode,
          });
      hydrateProject(nextProject);
      toast.success(project ? "Draft updated." : "Project created.");
    });
  };

  const runAssist = async () => {
    if (!storyInput.trim()) {
      toast.error("Write the rough story first.");
      return;
    }
    await withBusy("assist", async () => {
      const nextAssist = await requestStoryAssist({ story_text: storyInput, focus: assistFocus });
      setAssist(nextAssist);
      toast.success("Story assist ready.");
    });
  };

  const startAutomation = async () => {
    if (!project) { toast.error("Save the story draft before starting automation."); return; }
    try {
      const run = await startStoryAutomation(project.id, { style_id: styleId, detail_story: detailStory, narrative_style_variant_id: narrativeVariantId || null });
      setAutomationRun(run); toast.success("Automation started. You can navigate without losing the run.");
    } catch (error: any) { toast.error(error.message || "Unable to start automation"); }
  };

  const startProductionRun = async () => {
    if (!project) { toast.error("Save and complete planning automation first."); return; }
    if (NEW_PRODUCTION_NAV_ENABLED) {
      selectProductionProject(project.id);
      navigate("/production");
      return;
    }
    try { setProductionRun(await startProduction(project.id, true)); toast.success("Full production started. Outputs will remain available while you navigate."); }
    catch (error: any) { toast.error(error.message || "Unable to start full production"); }
  };

  const controlAutomation = async (action: "pause" | "resume" | "reset") => {
    if (!project) return;
    try { setAutomationRun(await actionStoryAutomation(project.id, action)); toast.success(action === "reset" ? "Run reset; project preserved." : `Run ${action}d.`); }
    catch (error: any) { toast.error(error.message || `Unable to ${action} run`); }
  };

  const renderArtifactEditor = (artifactType: ArtifactType) => {
    const artifact = project?.artifacts[artifactType];
    const previousType = artifactOrder[artifactOrder.indexOf(artifactType) - 1];
    const canGenerate = artifactType === "story" || Boolean(previousType && project?.artifacts[previousType].content);
    const status = artifact?.status || "pending";
    return (
      <Card key={artifactType} className="rounded-3xl">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>{artifactLabels[artifactType]}</CardTitle>
              <CardDescription>Generate, then edit directly before moving to the next stage.</CardDescription>
            </div>
            <Badge variant={status === "ready" ? "default" : "outline"}>{status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Button
              disabled={!project || !canGenerate || Boolean(busyKey)}
              onClick={() =>
                withBusy(`generate-${artifactType}`, async () => {
                  const nextProject = await generateArtifact(project!.id, artifactType);
                  hydrateProject(nextProject);
                  toast.success(`${artifactLabels[artifactType]} generated.`);
                })
              }
            >
              Generate
            </Button>
            <Button
              variant="outline"
              disabled={!project || !artifactDrafts[artifactType]?.trim() || Boolean(busyKey)}
              onClick={() =>
                withBusy(`save-${artifactType}`, async () => {
                  const content = JSON.parse(artifactDrafts[artifactType]);
                  const nextProject = await saveArtifact(project!.id, artifactType, content);
                  setArtifactDirty((current) => ({ ...current, [artifactType]: false }));
                  hydrateProject(nextProject);
                  toast.success(`${artifactLabels[artifactType]} saved.`);
                }).catch((error) => {
                  toast.error(error instanceof Error ? error.message : "Invalid JSON");
                })
              }
            >
              Save Edits
            </Button>
          </div>
          <Textarea
            className="min-h-[260px] font-mono text-xs"
            value={artifactDrafts[artifactType] || ""}
            onChange={(event) => {
              setArtifactDirty((current) => ({ ...current, [artifactType]: true }));
              setArtifactDrafts((current) => ({ ...current, [artifactType]: event.target.value }));
            }}
            placeholder={`No ${artifactType} artifact yet.`}
          />
        </CardContent>
      </Card>
    );
  };

  return (
    <AppShell>
      <section className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <Card className="rounded-3xl">
          <CardHeader>
            <Badge variant="outline" className="w-fit">Phase 2</Badge>
            <CardTitle>Editable story canvas</CardTitle>
            <CardDescription>
              Write rough thoughts, then use assist mode to refine, connect, clarify, or expand only when asked.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="title">Project Title</Label>
                <Input id="title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="flex items-center justify-between rounded-2xl border border-border px-4 py-3">
                <div>
                  <p className="text-sm font-medium">Automation mode</p>
                  <p className="text-xs text-muted-foreground">Reserved for later n8n-style chaining.</p>
                </div>
                <Switch checked={automationMode} onCheckedChange={setAutomationMode} />
              </div>
            </div>
            <div className="grid gap-4 rounded-2xl border border-primary/20 bg-primary/5 p-4 md:grid-cols-[1fr_auto] md:items-end">
              <div className="space-y-2"><ProductionStylePicker title="Production type and narrative style" value={styleId} variantId={narrativeVariantId} onChange={(type, variant) => { setStyleId(type); setNarrativeVariantId(variant); }} disabled={Boolean(automationRun && ["queued", "running"].includes(automationRun.status))} /><label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={detailStory} onChange={(event) => setDetailStory(event.target.checked)} /> Detail and refine the story before downstream stages</label></div>
              <div className="flex flex-wrap gap-2"><Button disabled={!project || Boolean(busyKey) || Boolean(automationRun && ["queued", "running", "paused"].includes(automationRun.status))} onClick={startAutomation}><Play className="mr-2 h-4 w-4" />Start planning</Button><Button variant="outline" disabled={!project || Boolean(busyKey) || Boolean(productionRun && ["queued", "running", "retrying"].includes(productionRun.status))} onClick={startProductionRun}><Sparkles className="mr-2 h-4 w-4" />{NEW_PRODUCTION_NAV_ENABLED ? "Open production workspace" : "Start full production"}</Button></div>
            </div>
            <Textarea
              className="min-h-[320px]"
              value={storyInput}
              onChange={(event) => setStoryInput(event.target.value)}
              placeholder="Dump the rough idea here. Bad English is fine. The assist mode should clarify intent, not flatten it."
            />
            <div className="flex flex-wrap gap-3">
              <Button disabled={Boolean(busyKey)} onClick={saveProjectDraft}>Save Draft</Button>
              <Button variant="outline" disabled={Boolean(busyKey)} onClick={runAssist}>
                <Sparkles className="mr-2 h-4 w-4" />
                Run Assist
              </Button>
              <select
                className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={assistFocus}
                onChange={(event) => setAssistFocus(event.target.value)}
              >
                <option value="refine">Refine</option>
                <option value="connect">Connect ideas</option>
                <option value="clarify">Clarify gaps</option>
                <option value="expand">Expand carefully</option>
              </select>
            </div>
            {automationRun ? <div className="rounded-2xl border border-border bg-background/80 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-medium">Automation run</p><p className="text-xs text-muted-foreground">{automationRun.current_stage} · {automationRun.status}</p></div><div className="flex gap-2">{automationRun.status === "running" ? <Button size="sm" variant="outline" onClick={() => controlAutomation("pause")}><Pause className="mr-1 h-3 w-3" />Pause</Button> : null}{automationRun.status === "paused" ? <Button size="sm" variant="outline" onClick={() => controlAutomation("resume")}><Play className="mr-1 h-3 w-3" />Resume</Button> : null}{["running", "paused"].includes(automationRun.status) ? <Button size="sm" variant="ghost" onClick={() => controlAutomation("reset")}><RotateCcw className="mr-1 h-3 w-3" />Reset</Button> : null}</div></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all duration-500" style={{ width: `${automationRun.progress}%` }} /></div>{automationRun.status === "running" ? <p className="mt-2 flex items-center text-xs text-muted-foreground"><Loader2 className="mr-1 h-3 w-3 animate-spin" />{automationRun.progress}% complete · safe pause points are respected</p> : null}{automationRun.error ? <p className="mt-2 text-xs text-destructive">{automationRun.error}</p> : null}</div> : null}
            {productionRun ? <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4"><div className="flex items-center justify-between"><div><p className="text-sm font-medium">Full production</p><p className="text-xs text-muted-foreground">{productionRun.stage} · {productionRun.status}</p></div><span className="text-xs tabular-nums">{productionRun.progress ?? 0}%</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all duration-500" style={{ width: `${productionRun.progress ?? 0}%` }} /></div>{productionRun.status === "running" ? <p className="mt-2 flex items-center text-xs text-muted-foreground"><Loader2 className="mr-1 h-3 w-3 animate-spin" />Rendering scenes and preserving project outputs</p> : null}{productionRun.error ? <p className="mt-2 text-xs text-destructive">{productionRun.error}</p> : null}</div> : null}
          </CardContent>
        </Card>

        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle>Assist Output</CardTitle>
            <CardDescription>Use this as a collaborator pane, not an auto-rewrite dump.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {assist ? (
              <>
                <div className="rounded-2xl border border-border p-4 text-sm">{assist.summary}</div>
                <div>
                  <p className="mb-2 text-sm font-medium">Questions</p>
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    {assist.questions.map((question) => (
                      <li key={question} className="rounded-xl border border-border p-3">{question}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">Recommendations</p>
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    {assist.recommendations.map((recommendation) => (
                      <li key={recommendation} className="rounded-xl border border-border p-3">
                        <Lightbulb className="mr-2 inline h-4 w-4 text-primary" />
                        {recommendation}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">Suggested revision</p>
                  <Textarea
                    className="min-h-[220px]"
                    value={assist.revised_text}
                    onChange={(event) => setAssist((current) => (current ? { ...current, revised_text: event.target.value } : current))}
                  />
                  <Button
                    variant="outline"
                    className="mt-3"
                    onClick={() => {
                      setStoryInput(assist.revised_text);
                      toast.success("Suggested revision applied to draft.");
                    }}
                  >
                    Apply To Draft
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Run assist after writing the draft.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="mt-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Story Pipeline</p>
            <p className="text-sm text-muted-foreground">
              {completedArtifacts}/{artifactOrder.length} artifacts generated. Edit each artifact before moving on.
            </p>
          </div>
          {project ? <Badge variant="outline">{project.runtime.current_task}</Badge> : null}
        </div>
        <div className="grid gap-6 xl:grid-cols-2">{artifactOrder.map(renderArtifactEditor)}</div>
      </section>
    </AppShell>
  );
}
