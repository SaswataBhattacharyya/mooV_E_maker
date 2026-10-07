import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { ArrowRight, Film, Library, PenTool, Workflow } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CURRENT_PROJECT_KEY, fetchProject, type ProjectState } from "@/lib/project-api";

export default function Home() {
  const [project, setProject] = useState<ProjectState | null>(null);

  useEffect(() => {
    const projectId = localStorage.getItem(CURRENT_PROJECT_KEY);
    if (!projectId) {
      return;
    }
    fetchProject(projectId).then(setProject).catch(() => {
      localStorage.removeItem(CURRENT_PROJECT_KEY);
    });
  }, []);

  return (
    <AppShell>
      <section className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card className="rounded-3xl border-border bg-card/95">
          <CardHeader>
            <Badge variant="outline" className="w-fit">Phase 1-3 Workspace</Badge>
            <CardTitle className="mt-3 text-4xl leading-tight">One app, separate modules, shared project state.</CardTitle>
            <CardDescription className="max-w-2xl text-base">
              Build and refine the story first, then move approved prompts into the media composer where workflow-aware
              ComfyUI forms handle image and video generation.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/story">
                Open Story Builder
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/media">Open Media Composer</Link>
            </Button>
          </CardContent>
        </Card>

        <Card className="rounded-3xl border-border bg-card/95">
          <CardHeader>
            <CardTitle>Current Project</CardTitle>
            <CardDescription>The Story and Media routes both use this shared project context.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {project ? (
              <>
                <div className="rounded-2xl border border-border p-4">
                  <p className="font-medium">{project.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{project.current_stage}</p>
                  <p className="mt-3 text-xs text-muted-foreground">{project.runtime.current_task}</p>
                </div>
                <Button asChild className="w-full">
                  <Link to="/story">Continue Project</Link>
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No project yet. Start in the Story Builder.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="mt-6 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {[
          {
            icon: PenTool,
            title: "Story Builder",
            text: "Editable canvas, stage-by-stage artifacts, and assist mode that clarifies rather than blindly inflating the story.",
          },
          {
            icon: Film,
            title: "Media Composer",
            text: "Workflow-aware ComfyUI inputs for text, images, start/end frames, and later audio/video branches.",
          },
          {
            icon: Workflow,
            title: "Automation",
            text: "Reserved for the later n8n-style runner that chains Story and Media modules with human or Hermes checkpoints.",
          },
          {
            icon: Library,
            title: "Video Repertoire",
            text: "Download, upload, analyze, search, and reuse reference videos with scene-level summaries and clips.",
          },
        ].map((item) => (
          <Card key={item.title} className="rounded-3xl">
            <CardHeader>
              <item.icon className="h-5 w-5 text-primary" />
              <CardTitle>{item.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{item.text}</CardContent>
          </Card>
        ))}
      </section>
    </AppShell>
  );
}
