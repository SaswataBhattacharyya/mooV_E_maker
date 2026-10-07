import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createMediaJob,
  CURRENT_PROJECT_KEY,
  fetchProject,
  getProjectFileUrl,
  listMediaJobs,
  listWorkflows,
  searchVideoReferences,
  nextVideoReferencePage,
  listSeoStyles,
  createSeoStyle,
  selectVideoReferences,
  getVideoReferenceContentUrl,
  getVideoReferenceThumbnailUrl,
  type SeoStyle,
  type VideoReferenceResult,
  type ProjectState,
  type WorkflowManifest,
} from "@/lib/project-api";

export default function MediaComposer() {
  const [project, setProject] = useState<ProjectState | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowManifest[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [numberFields, setNumberFields] = useState<Record<string, string>>({});
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [mediaJobs, setMediaJobs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [referenceQuery, setReferenceQuery] = useState("");
  const [referenceTopN, setReferenceTopN] = useState(5);
  const [referenceSort, setReferenceSort] = useState("subscene");
  const [referenceResults, setReferenceResults] = useState<VideoReferenceResult[]>([]);
  const [referenceSearchId, setReferenceSearchId] = useState<string | null>(null);
  const [referenceHasMore, setReferenceHasMore] = useState(false);
  const [referenceBusy, setReferenceBusy] = useState(false);
  const [seoEnabled, setSeoEnabled] = useState(false);
  const [seoStyles, setSeoStyles] = useState<SeoStyle[]>([]);
  const [seoStyleId, setSeoStyleId] = useState("");
  const [minDuration, setMinDuration] = useState("");
  const [maxDuration, setMaxDuration] = useState("");

  useEffect(() => {
    const projectId = localStorage.getItem(CURRENT_PROJECT_KEY);
    if (projectId) {
      fetchProject(projectId).then(setProject).catch(() => localStorage.removeItem(CURRENT_PROJECT_KEY));
      listMediaJobs(projectId).then(setMediaJobs).catch(() => undefined);
    }
    listWorkflows()
      .then((items) => {
        setWorkflows(items);
        const preferred = items.find((item) => item.supports_api_submission) || items[0];
        if (preferred) {
          setSelectedWorkflowId(preferred.id);
        }
      })
      .catch((error) => toast.error(error.message || "Failed to load workflows"));
    listSeoStyles().then(setSeoStyles).catch(() => undefined);
  }, []);

  const searchReferences = async () => {
    if (!referenceQuery.trim()) { toast.error("Describe the clip you need first."); return; }
    setReferenceBusy(true);
    try {
      const result = await searchVideoReferences({ query: referenceQuery, top_n: referenceTopN, sort_level: referenceSort, filters: { ...(minDuration ? { min_duration_sec: Number(minDuration) } : {}), ...(maxDuration ? { max_duration_sec: Number(maxDuration) } : {}) }, seo_enabled: seoEnabled, style_id: seoEnabled ? seoStyleId || null : null });
      setReferenceSearchId(result.search_id); setReferenceResults(result.results); setReferenceHasMore(result.has_more);
      if (!result.results.length) toast.info("No curated clips matched. Add videos to video_summariser/out_videos and index them.");
    } catch (error: any) { toast.error(error.message || "Reference search failed"); }
    finally { setReferenceBusy(false); }
  };
  const nextReferences = async () => {
    if (!referenceSearchId) return;
    setReferenceBusy(true);
    try { const result = await nextVideoReferencePage(referenceSearchId, referenceTopN); setReferenceResults((current) => [...current, ...result.results]); setReferenceHasMore(result.has_more); }
    catch (error: any) { toast.error(error.message || "Unable to load more references"); }
    finally { setReferenceBusy(false); }
  };
  const addSeoStyle = async () => {
    const name = window.prompt("Name this SEO style");
    if (!name?.trim()) return;
    try { const style = await createSeoStyle({ name: name.trim(), terms: referenceQuery.split(/[,;]+/).map((term) => term.trim()).filter(Boolean), avoid_terms: [], weights: { action: 2, camera: 1, lighting: 1, style: 1 } }); setSeoStyles((current) => [...current, style]); setSeoStyleId(style.style_id); setSeoEnabled(true); toast.success("SEO style created"); }
    catch (error: any) { toast.error(error.message || "Unable to create style"); }
  };

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) || null,
    [selectedWorkflowId, workflows]
  );

  useEffect(() => {
    if (!selectedWorkflow) {
      return;
    }
    const nextFields: Record<string, string> = {};
    for (const field of selectedWorkflow.fields) {
      if (field.kind === "number" && field.default != null) {
        nextFields[field.key] = String(field.default);
      }
      if (field.key === "negative_prompt" && field.default) {
        setNegativePrompt(String(field.default));
      }
    }
    setNumberFields(nextFields);
  }, [selectedWorkflow]);

  const handleSubmit = async () => {
    if (!project) {
      toast.error("Create a project in Story Builder first.");
      return;
    }
    if (!selectedWorkflow) {
      toast.error("Choose a workflow first.");
      return;
    }
    setBusy(true);
    try {
      const payload: Record<string, any> = {
        workflow_id: selectedWorkflow.id,
        prompt,
        negative_prompt: negativePrompt,
      };
      for (const [key, value] of Object.entries(numberFields)) {
        if (value.trim()) {
          payload[key] = Number(value);
        }
      }
      const response = await createMediaJob(project.id, payload, imageFiles);
      setProject(response.project);
      setMediaJobs((current) => [response.job, ...current]);
      toast.success("Media job completed.");
    } catch (error: any) {
      toast.error(error.message || "Media job failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Card className="rounded-3xl xl:col-span-2">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><Badge variant="outline" className="w-fit">Reference library</Badge><CardTitle className="mt-2">Video Clip Selection</CardTitle><CardDescription>Search only the curated videos placed in video_summariser/out_videos. Approved clips can be reused across projects.</CardDescription></div>
              <Button variant="outline" onClick={() => setReferenceResults([])}>Clear results</Button>
            </div>
          </CardHeader>
          <CardContent>
            <details open className="rounded-2xl border border-border p-4">
              <summary className="cursor-pointer font-medium">Search and rank clip references</summary>
              <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_auto_auto]">
                <Textarea value={referenceQuery} onChange={(event) => setReferenceQuery(event.target.value)} placeholder="Example: fast two-person sword fight, overhead parry, side-tracking camera" className="min-h-[100px]" />
                <div className="space-y-3"><Label>Top N</Label><Input type="number" min={1} max={50} value={referenceTopN} onChange={(event) => setReferenceTopN(Math.max(1, Math.min(50, Number(event.target.value) || 5)))} /><Label>Sort level</Label><select className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={referenceSort} onChange={(event) => setReferenceSort(event.target.value)}><option value="scene">Scene</option><option value="subscene">Sub-scene</option><option value="clip">Clip/Cut</option></select><div className="grid grid-cols-2 gap-2"><Input aria-label="Minimum duration" type="number" min={0} placeholder="Min sec" value={minDuration} onChange={(event) => setMinDuration(event.target.value)} /><Input aria-label="Maximum duration" type="number" min={0} placeholder="Max sec" value={maxDuration} onChange={(event) => setMaxDuration(event.target.value)} /></div></div>
                <div className="space-y-3"><Label>SEO weighting</Label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={seoEnabled} onChange={(event) => setSeoEnabled(event.target.checked)} /> Apply SEO style</label><select disabled={!seoEnabled} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={seoStyleId} onChange={(event) => setSeoStyleId(event.target.value)}><option value="">No SEO</option>{seoStyles.map((style) => <option key={style.style_id} value={style.style_id}>{style.name}</option>)}</select><Button variant="outline" onClick={addSeoStyle}>Create SEO style</Button><Button disabled={referenceBusy} onClick={searchReferences}>{referenceBusy ? "Searching..." : "Search clips"}</Button></div>
              </div>
            </details>
            {referenceResults.length ? <div className="mt-5 space-y-4">{Object.entries(referenceResults.reduce<Record<string, VideoReferenceResult[]>>((groups, item) => { (groups[item.source_video] ||= []).push(item); return groups; }, {})).map(([source, clips]) => <div key={source} className="rounded-2xl border border-border p-4"><p className="mb-3 text-sm font-medium">{source}</p><div className="flex gap-4 overflow-x-auto pb-2">{clips.map((clip) => <div key={clip.clip_id} className="min-w-[260px] rounded-xl border border-border p-3"><img alt={`${clip.scene_id} thumbnail`} className="mb-3 aspect-video w-full rounded-lg bg-black object-cover" src={getVideoReferenceThumbnailUrl(clip.clip_id)} onError={(event) => { event.currentTarget.style.display = "none"; }} /><video controls preload="metadata" className="mb-3 aspect-video w-full rounded-lg bg-black" src={getVideoReferenceContentUrl(clip.clip_id)} /><p className="line-clamp-3 text-sm">{clip.summary}</p><p className="mt-2 text-xs text-muted-foreground">{clip.scene_id} · {clip.subscene_id} · {clip.start_time_sec.toFixed(1)}s · score {(clip.match_score * 100).toFixed(0)}%</p><p className="mt-1 text-xs text-muted-foreground">{clip.match_reason}</p><Button className="mt-3 w-full" variant="outline" disabled={!project} onClick={() => project && selectVideoReferences(project.id, [clip]).then(() => toast.success("Clip approved for this project")).catch((error: any) => toast.error(error.message || "Selection failed"))}>Approve clip</Button></div>)}</div></div>)}</div> : <p className="mt-5 text-sm text-muted-foreground">Search the curated corpus to populate clip carousels. Results are transient until you approve a clip.</p>}
            {referenceHasMore ? <Button className="mt-4" variant="outline" disabled={referenceBusy} onClick={nextReferences}>Next top {referenceTopN}</Button> : null}
          </CardContent>
        </Card>
        <Card className="rounded-3xl">
          <CardHeader>
            <Badge variant="outline" className="w-fit">Phase 3</Badge>
            <CardTitle>Workflow-aware ComfyUI forms</CardTitle>
            <CardDescription>
              Select a workflow, fill the required prompt and asset inputs, and submit supported API workflows to ComfyUI.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="workflow">Workflow</Label>
              <select
                id="workflow"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={selectedWorkflowId}
                onChange={(event) => setSelectedWorkflowId(event.target.value)}
              >
                {workflows.map((workflow) => (
                  <option key={workflow.id} value={workflow.id}>
                    {workflow.category}: {workflow.label}
                  </option>
                ))}
              </select>
            </div>
            {selectedWorkflow ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{selectedWorkflow.category}</Badge>
                  <Badge variant="outline">{selectedWorkflow.output_type}</Badge>
                  <Badge variant={selectedWorkflow.supports_api_submission ? "default" : "secondary"}>
                    {selectedWorkflow.supports_api_submission ? "Runnable" : "Catalog only"}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{selectedWorkflow.recommended_use_case}</p>
                <div className="space-y-2">
                  <Label>Prompt</Label>
                  <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} className="min-h-[160px]" />
                </div>
                {selectedWorkflow.fields.some((field) => field.key === "negative_prompt") ? (
                  <div className="space-y-2">
                    <Label>Negative Prompt</Label>
                    <Textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} className="min-h-[120px]" />
                  </div>
                ) : null}
                <div className="grid gap-4 md:grid-cols-2">
                  {selectedWorkflow.fields
                    .filter((field) => field.kind === "number")
                    .map((field) => (
                      <div key={field.key} className="space-y-2">
                        <Label>{field.label}</Label>
                        <Input
                          value={numberFields[field.key] || ""}
                          onChange={(event) => setNumberFields((current) => ({ ...current, [field.key]: event.target.value }))}
                        />
                      </div>
                    ))}
                </div>
                {selectedWorkflow.fields.some((field) => field.kind === "image") ? (
                  <div className="space-y-2">
                    <Label>Image Inputs</Label>
                    <Input
                      type="file"
                      multiple
                      accept="image/*"
                      onChange={(event) => setImageFiles(Array.from(event.target.files || []))}
                    />
                    <p className="text-xs text-muted-foreground">
                      Uploaded files are passed to the workflow in the order selected.
                    </p>
                  </div>
                ) : null}
                <Button disabled={busy || !selectedWorkflow.supports_api_submission} onClick={handleSubmit}>
                  {busy ? "Submitting..." : "Run Workflow"}
                </Button>
              </>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="rounded-3xl">
            <CardHeader>
              <CardTitle>Project Hand-off</CardTitle>
              <CardDescription>
                Approved story prompts should move from Story Builder into this module. Current project context is shown here.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {project ? (
                <div className="space-y-2 rounded-2xl border border-border p-4">
                  <p className="font-medium">{project.title}</p>
                  <p className="text-sm text-muted-foreground">{project.current_stage}</p>
                  <p className="text-xs text-muted-foreground">{project.runtime.current_task}</p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Create a Story Builder project first.</p>
              )}
            </CardContent>
          </Card>

          <Card className="rounded-3xl">
            <CardHeader>
              <CardTitle>Recent Media Jobs</CardTitle>
              <CardDescription>Outputs generated through the API-compatible workflows.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {mediaJobs.length ? (
                mediaJobs.map((job) => (
                  <div key={job.job_id} className="rounded-2xl border border-border p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-medium">{job.workflow_id}</p>
                        <p className="text-xs text-muted-foreground">{job.prompt_id}</p>
                      </div>
                      <Badge variant="outline">{job.status}</Badge>
                    </div>
                    <p className="mt-3 text-sm text-muted-foreground">{job.prompt}</p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {job.outputs?.map((output: any) =>
                        output.kind === "image" ? (
                          <img
                            key={output.relative_path}
                            src={getProjectFileUrl(project!.id, output.relative_path)}
                            alt={job.workflow_id}
                            className="rounded-xl border border-border"
                          />
                        ) : (
                          <video
                            key={output.relative_path}
                            controls
                            className="w-full rounded-xl border border-border"
                            src={getProjectFileUrl(project!.id, output.relative_path)}
                          />
                        )
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No media jobs yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}
