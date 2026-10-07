import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Image as ImageIcon, PauseCircle, PlayCircle, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  acceptImageCandidate,
  continueProject,
  CURRENT_PROJECT_KEY,
  createImageBatch,
  createMoreImageBatch,
  createProject,
  fetchProject,
  INTAKE_DRAFT_KEY,
  generateArtifact,
  getProjectFileUrl,
  pauseProject,
  resetProject,
  saveArtifact,
  updateProjectDraft,
  getSupervisorUrl,
  type ArtifactType,
  type ImageBatch,
  type ProjectState,
} from "@/lib/project-api";

const artifactOrder: ArtifactType[] = ["story", "characters", "scenes", "subscenes", "dialogue", "image_jobs"];

const panelClass = "rounded-3xl border border-border bg-card/95 shadow-sm";

const artifactLabels: Record<ArtifactType, string> = {
  story: "Expanded Story",
  characters: "Character Sheet",
  scenes: "Scene Plan",
  subscenes: "Sub-scene Direction",
  dialogue: "Dialogue Plan",
  image_jobs: "Image Queue",
};

const Index = () => {
  const [artifactDirty, setArtifactDirty] = useState<Record<string, boolean>>({});
  const [title, setTitle] = useState("");
  const [storyInput, setStoryInput] = useState("");
  const [automationMode, setAutomationMode] = useState(false);
  const [project, setProject] = useState<ProjectState | null>(null);
  const [artifactDrafts, setArtifactDrafts] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  useEffect(() => {
    const savedDraft = localStorage.getItem(INTAKE_DRAFT_KEY);
    if (savedDraft) {
      try {
        const parsed = JSON.parse(savedDraft);
        setTitle(parsed.title || "");
        setStoryInput(parsed.storyInput || "");
        setAutomationMode(Boolean(parsed.automationMode));
      } catch {
        // ignore corrupt local draft
      }
    }

    const savedProjectId = localStorage.getItem(CURRENT_PROJECT_KEY);
    if (!savedProjectId) {
      return;
    }
    fetchProject(savedProjectId)
      .then((nextProject) => {
        setProjectAndDrafts(nextProject);
        setTitle(nextProject.title);
        setStoryInput(nextProject.story_input);
        setAutomationMode(nextProject.automation_mode);
      })
      .catch(() => {
        localStorage.removeItem(CURRENT_PROJECT_KEY);
      });
  }, []);

  useEffect(() => {
    localStorage.setItem(
      INTAKE_DRAFT_KEY,
      JSON.stringify({
        title,
        storyInput,
        automationMode,
      })
    );
  }, [title, storyInput, automationMode]);

  const latestBatch = useMemo<ImageBatch | null>(() => {
    if (!project) {
      return null;
    }
    const batches = project.image_queue.batches;
    return batches.length ? batches[batches.length - 1] : null;
  }, [project]);

  const currentJobTitle = useMemo(() => {
    if (!project) {
      return null;
    }
    const imageJobs = project.artifacts.image_jobs.content?.jobs || [];
    return imageJobs[project.image_queue.current_index]?.title || null;
  }, [project]);

  useEffect(() => {
    if (!latestBatch) {
      setSelectedCandidateId(null);
      return;
    }
    if (latestBatch.status === "accepted") {
      setSelectedCandidateId(latestBatch.selected_candidate_id || latestBatch.candidates[0]?.candidate_id || null);
      return;
    }
    setSelectedCandidateId(latestBatch.candidates[0]?.candidate_id || null);
  }, [latestBatch]);

  const setProjectAndDrafts = (nextProject: ProjectState, options?: { preserveDirty?: boolean }) => {
    const preserveDirty = options?.preserveDirty ?? false;
    setProject(nextProject);
    localStorage.setItem(CURRENT_PROJECT_KEY, nextProject.id);
    setArtifactDrafts((current) => {
      const nextDrafts: Record<string, string> = { ...current };
      for (const artifactType of artifactOrder) {
        const content = nextProject.artifacts[artifactType].content;
        if (preserveDirty && artifactDirty[artifactType]) {
          continue;
        }
        nextDrafts[artifactType] = content ? JSON.stringify(content, null, 2) : "";
      }
      return nextDrafts;
    });
  };

  useEffect(() => {
    if (!project) {
      return;
    }

    const shouldPoll =
      project.runtime.automation_active ||
      ["RUNNING", "PAUSED", "FAILED"].includes(project.runtime.state) ||
      project.status === "automating";

    if (!shouldPoll) {
      return;
    }

    const intervalId = window.setInterval(() => {
      fetchProject(project.id)
        .then((nextProject) => {
          setProjectAndDrafts(nextProject, { preserveDirty: true });
        })
        .catch(() => {
          // ignore transient polling failures
        });
    }, 1500);

    return () => window.clearInterval(intervalId);
  }, [artifactDirty, project]);

  const withBusy = async (key: string, action: () => Promise<ProjectState>, successMessage: string) => {
    setBusyKey(key);
    try {
      const nextProject = await action();
      setProjectAndDrafts(nextProject);
      toast.success(successMessage);
    } catch (error: any) {
      toast.error(error.message || "Request failed");
    } finally {
      setBusyKey(null);
    }
  };

  const handleCreateProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !storyInput.trim()) {
      toast.error("Project title and story input are required.");
      return;
    }
    setBusyKey("create-project");
    try {
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
      setArtifactDirty({});
      setProjectAndDrafts(nextProject);
      toast.success(project ? "Draft updated." : "Draft saved.");
      if (automationMode && typeof window !== "undefined") {
        window.open(getSupervisorUrl(nextProject.id), "_blank", "noopener,noreferrer");
      }
    } catch (error: any) {
      toast.error(error.message || "Failed to save draft");
    } finally {
      setBusyKey(null);
    }
  };

  const renderArtifactEditor = (artifactType: ArtifactType) => {
    const artifact = project?.artifacts[artifactType];
    const draft = artifactDrafts[artifactType] || "";
    const generateDisabled =
      !project ||
      (artifactType !== "story" && !project.artifacts[artifactOrder[artifactOrder.indexOf(artifactType) - 1]].content);
    const statusVariant =
      artifact?.status === "ready"
        ? "default"
        : artifact?.status === "generating" || artifact?.status === "generated" || artifact?.status === "reviewing"
          ? "outline"
          : "secondary";

    return (
      <Card key={artifactType} className={panelClass}>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>{artifactLabels[artifactType]}</CardTitle>
              <CardDescription>
                Generate with the local LLM, then edit the JSON directly if needed.
              </CardDescription>
            </div>
            <Badge variant={statusVariant}>
              {artifact?.status || "pending"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Button
              onClick={() =>
                withBusy(
                  `generate-${artifactType}`,
                  () => generateArtifact(project!.id, artifactType),
                  `${artifactLabels[artifactType]} generated.`
                )
              }
              disabled={generateDisabled || busyKey !== null}
            >
              Generate
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                try {
                  withBusy(
                    `save-${artifactType}`,
                    async () => {
                      const result = await saveArtifact(project!.id, artifactType, JSON.parse(draft));
                      setArtifactDirty((current) => ({ ...current, [artifactType]: false }));
                      return result;
                    },
                    `${artifactLabels[artifactType]} saved.`
                  );
                } catch (error: any) {
                  toast.error(error.message || "JSON is invalid.");
                }
              }}
              disabled={!project || !draft.trim() || busyKey !== null}
            >
              Save Edits
            </Button>
          </div>
          <Textarea
            className="min-h-[280px] font-mono text-xs"
            value={draft}
            onChange={(event) => {
              setArtifactDirty((current) => ({ ...current, [artifactType]: true }));
              setArtifactDrafts((current) => ({
                ...current,
                [artifactType]: event.target.value,
              }));
            }}
            placeholder={`No ${artifactType} artifact yet.`}
          />
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-primary">Director Workspace</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-foreground">
              Story to Image Orchestration
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              Build the story, character, scene, sub-scene, dialogue, and image queue artifacts first, then review
              4-image ComfyUI batches before moving forward.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              The first save creates the project. If full automation is on, that save also starts Ripa supervision and
              opens the live feed on port 3009.
            </p>
          </div>
          <Link
            to="/agent-status"
            className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
          >
            Agent Status
          </Link>
          <a
            href={getSupervisorUrl(project?.id ?? localStorage.getItem(CURRENT_PROJECT_KEY))}
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
          >
            Supervisor
          </a>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <Card className={panelClass}>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Project Intake</CardTitle>
                  <CardDescription>
                    The initial story is the only free-form user input. Everything else is generated, reviewed, and
                    edited in structured layers.
                  </CardDescription>
                </div>
                <Sparkles className="h-5 w-5 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleCreateProject}>
                <div className="space-y-2">
                  <Label htmlFor="project-title">Project Title</Label>
                  <Input
                    id="project-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="The Glass Train at Dawn"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="story-input">Initial Story Input</Label>
                  <Textarea
                    id="story-input"
                    className="min-h-[180px]"
                    value={storyInput}
                    onChange={(event) => setStoryInput(event.target.value)}
                    placeholder="Describe the story idea, target length, tone, setting, and any characters the story must include."
                  />
                </div>
                <div className="flex items-center justify-between rounded-2xl border border-border bg-secondary/60 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">Fully automate approvals</p>
                    <p className="text-xs text-muted-foreground">
                      The pipeline still shows its choices in the website, but it can continue without waiting.
                    </p>
                  </div>
                  <Switch checked={automationMode} onCheckedChange={setAutomationMode} />
                </div>
                <Button type="submit" disabled={busyKey === "create-project"}>
                  {busyKey === "create-project" ? "Saving..." : project ? "Save Draft" : "Save Draft"}
                </Button>
              </form>
            </CardContent>
          </Card>

          {project ? (
            <>
              <Card className={panelClass}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <CardTitle>{project.title}</CardTitle>
                      <CardDescription>
                        Project ID: <span className="font-mono">{project.id}</span>
                      </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{project.status}</Badge>
                      <Badge variant="outline">{project.current_stage}</Badge>
                      {project.runtime.automation_active ? <Badge variant="outline">Automation live</Badge> : null}
                      {project.runtime.supervisor?.mode ? (
                        <Badge variant="outline">Ripa: {project.runtime.supervisor.mode}</Badge>
                      ) : null}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-3">
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={() => withBusy("pause", () => pauseProject(project.id), "Project paused.")}
                    disabled={busyKey !== null}
                  >
                    <PauseCircle className="h-4 w-4" />
                    Stop
                  </Button>
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={() => withBusy("continue", () => continueProject(project.id), "Project resumed.")}
                    disabled={busyKey !== null}
                  >
                    <PlayCircle className="h-4 w-4" />
                    Continue
                  </Button>
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={() => withBusy("reset", () => resetProject(project.id), "Project reset.")}
                    disabled={busyKey !== null}
                  >
                    <RotateCcw className="h-4 w-4" />
                    Reset
                  </Button>
                </CardContent>
                <CardContent className="pt-0">
                  <p className="text-xs text-muted-foreground">
                    Context chain: story -&gt; characters -&gt; scenes -&gt; sub-scenes -&gt; dialogue -&gt; image queue.
                    Graphify and OpenClaw supervision remain optional later layers.
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">{project.runtime.current_task}</p>
                  {project.runtime.last_error ? (
                    <p className="mt-2 text-xs text-destructive">{project.runtime.last_error}</p>
                  ) : null}
                  {project.runtime.supervisor?.actionable_diagnosis ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Ripa: {project.runtime.supervisor.actionable_diagnosis.reason} Next:{" "}
                      {project.runtime.supervisor.actionable_diagnosis.next_action}
                    </p>
                  ) : null}
                </CardContent>
              </Card>

              {artifactOrder.map((artifactType) => renderArtifactEditor(artifactType))}
            </>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card className={panelClass}>
            <CardHeader>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <CardTitle>Image Review</CardTitle>
                  <CardDescription>
                    Generate 4 candidates for the current image job and accept one before moving to the next prompt.
                  </CardDescription>
                </div>
                <ImageIcon className="h-5 w-5 text-primary" />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {project ? (
                <>
                  <div className="rounded-2xl border border-border bg-secondary/50 p-4">
                    <p className="text-sm font-medium text-foreground">
                      Current queue item: {currentJobTitle || "No image job selected yet"}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Accepted images: {project.image_queue.accepted.length}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      onClick={() => withBusy("image-batch", () => createImageBatch(project.id, 4), "Image batch created.")}
                      disabled={!project.artifacts.image_jobs.content || busyKey !== null}
                    >
                      Generate 4 Candidates
                    </Button>
                  </div>
                  {latestBatch ? (
                    <div className="space-y-4">
                      <div className="rounded-2xl border border-border p-4">
                        <p className="text-sm font-semibold text-foreground">{latestBatch.title}</p>
                        <p className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{latestBatch.prompt}</p>
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        {latestBatch.candidates.map((candidate, index) => {
                          const isSelected = selectedCandidateId === candidate.candidate_id;
                          return (
                          <button
                            key={candidate.candidate_id}
                            type="button"
                            onClick={() => setSelectedCandidateId(candidate.candidate_id)}
                            className={`rounded-2xl border bg-card p-3 text-left transition-colors ${
                              isSelected ? "border-primary ring-1 ring-primary" : "border-border"
                            }`}
                            disabled={latestBatch.status === "accepted"}
                          >
                            <img
                              src={getProjectFileUrl(project.id, candidate.relative_path)}
                              alt={`Option ${index + 1}`}
                              className="aspect-video w-full rounded-xl border border-border object-cover"
                            />
                            <div className="mt-3 flex items-center justify-between gap-2">
                              <div>
                                <p className="text-sm font-medium text-foreground">Option {index + 1}</p>
                                <p className="text-xs text-muted-foreground">Seed {candidate.seed}</p>
                              </div>
                              {isSelected ? <Badge>Selected</Badge> : null}
                            </div>
                          </button>
                        )})}
                      </div>
                      <div className="flex flex-wrap gap-3">
                        <Button
                          onClick={() =>
                            withBusy(
                              `accept-${selectedCandidateId}`,
                              () => acceptImageCandidate(project.id, latestBatch.batch_id, selectedCandidateId!),
                              "Candidate accepted."
                            )
                          }
                          disabled={
                            busyKey !== null || latestBatch.status === "accepted" || !selectedCandidateId
                          }
                        >
                          Accept Selected
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() =>
                            withBusy(
                              "image-more",
                              () => createMoreImageBatch(project.id, latestBatch.batch_id, 4),
                              "Another batch created."
                            )
                          }
                          disabled={busyKey !== null || latestBatch.status === "accepted"}
                        >
                          Redo 4 More
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No image batch yet. Generate and approve the structured artifacts first, then start the review loop.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Create a project first to unlock image review.</p>
              )}
            </CardContent>
          </Card>

          <Card className={panelClass}>
            <CardHeader>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <CardTitle>Live Project Log</CardTitle>
                  <CardDescription>Backend events for the current project.</CardDescription>
                </div>
                <Bot className="h-5 w-5 text-primary" />
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {project?.logs?.length ? (
                project.logs
                  .slice()
                  .reverse()
                  .map((log) => (
                    <div key={log.id} className="rounded-2xl border border-border bg-secondary/40 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <Badge variant="outline">{log.level}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-foreground">{log.message}</p>
                    </div>
                  ))
              ) : (
                <p className="text-sm text-muted-foreground">No project log yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default Index;
