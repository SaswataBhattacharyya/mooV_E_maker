import { useEffect, useState } from "react";
import { Check, Mic2, Upload } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CURRENT_PROJECT_KEY, createReconstructionPart, getReconstructionSession, listProjects, saveReconstructionCalibration, uploadReconstructionTake, type ProjectState, type ReconstructionSession } from "@/lib/project-api";

export default function AudioReconstruct() {
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [projectId, setProjectId] = useState(localStorage.getItem(CURRENT_PROJECT_KEY) || "");
  const [session, setSession] = useState<ReconstructionSession | null>(null);
  const [character, setCharacter] = useState("");
  const [sentence, setSentence] = useState("This is my calibration sentence for the character voice.");
  const [partId, setPartId] = useState("scene_001_line_001");
  const [sequence, setSequence] = useState(1);
  const [expected, setExpected] = useState("");
  const [recording, setRecording] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { listProjects().then(setProjects).catch(() => undefined); }, []);
  useEffect(() => { if (projectId) getReconstructionSession(projectId).then(setSession).catch(() => undefined); }, [projectId]);
  const calibrate = async () => { if (!projectId || !character.trim()) return toast.error("Select a project and enter a character"); setBusy(true); try { setSession(await saveReconstructionCalibration(projectId, { character_name: character, sentence })); toast.success("Calibration saved"); } catch (e) { toast.error(e instanceof Error ? e.message : "Calibration failed"); } finally { setBusy(false); } };
  const preparePart = async () => { if (!projectId) return toast.error("Select a project"); setBusy(true); try { await createReconstructionPart(projectId, { part_id: partId, character_name: character, sequence, expected_text: expected }); setSession(await getReconstructionSession(projectId)); toast.success("Dialogue part highlighted"); } catch (e) { toast.error(e instanceof Error ? e.message : "Could not prepare part"); } finally { setBusy(false); } };
  const upload = async () => { if (!projectId || !recording) return toast.error("Choose a recording"); setBusy(true); try { await uploadReconstructionTake(projectId, partId, recording, expected); setSession(await getReconstructionSession(projectId)); setRecording(null); toast.success("Take saved; acceptance remains explicit"); } catch (e) { toast.error(e instanceof Error ? e.message : "Could not save take"); } finally { setBusy(false); } };
  return <AppShell><div className="space-y-6"><div><Badge variant="outline">Phase 3 · Audio Reconstruct</Badge><h2 className="mt-3 text-3xl font-semibold">Part-by-part dialogue recording</h2><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Calibrate each character first, then record one highlighted dialogue part at a time. Raw takes remain recoverable and ASR acceptance is explicit.</p></div>
    <Card className="rounded-3xl"><CardHeader><CardTitle>Project</CardTitle></CardHeader><CardContent><select aria-label="Project" className="h-10 w-full rounded-md border border-input bg-background px-3" value={projectId} onChange={e => { setProjectId(e.target.value); localStorage.setItem(CURRENT_PROJECT_KEY, e.target.value); }}><option value="">Select project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></CardContent></Card>
    <div className="grid gap-6 lg:grid-cols-2"><Card className="rounded-3xl"><CardHeader><CardTitle className="flex items-center gap-2"><Mic2 className="h-5 w-5"/>Character calibration</CardTitle><CardDescription>One common sentence establishes the character voice overlay/RVC settings.</CardDescription></CardHeader><CardContent className="space-y-4"><div><Label>Character</Label><Input className="mt-2" value={character} onChange={e => setCharacter(e.target.value)} placeholder="Alice"/></div><div><Label>Calibration sentence</Label><Textarea className="mt-2" value={sentence} onChange={e => setSentence(e.target.value)}/></div><Button disabled={busy} onClick={calibrate}>{busy ? "Saving…" : "Save calibration"}</Button>{session?.characters.map(c => <div className="flex items-center justify-between rounded-xl border p-3 text-sm" key={c.character_id}><span>{c.name}</span><Badge><Check className="mr-1 h-3 w-3"/>{c.status}</Badge></div>)}</CardContent></Card>
      <Card className="rounded-3xl"><CardHeader><CardTitle>Highlighted dialogue part</CardTitle><CardDescription>Prepare a line, then upload a raw take. Repeating creates a new immutable take.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 sm:grid-cols-2"><div><Label>Part ID</Label><Input className="mt-2" value={partId} onChange={e => setPartId(e.target.value)}/></div><div><Label>Sequence</Label><Input className="mt-2" type="number" min={1} value={sequence} onChange={e => setSequence(Number(e.target.value))}/></div></div><div><Label>Expected dialogue</Label><Textarea className="mt-2" value={expected} onChange={e => setExpected(e.target.value)} placeholder="The line the ASR should check"/></div><Button variant="outline" disabled={busy} onClick={preparePart}>Highlight part</Button><div><Label htmlFor="raw-recording">Raw recording</Label><Input id="raw-recording" className="mt-2" type="file" accept="audio/*" onChange={e => setRecording(e.target.files?.[0] || null)}/></div><Button disabled={busy || !recording} onClick={upload}><Upload className="mr-2 h-4 w-4"/>Save take</Button>{session?.parts.map(p => <div className="rounded-xl border p-3 text-sm" key={p.part_id}><div className="flex justify-between"><span>{p.character_name}_{p.sequence}</span><Badge variant={p.accepted_take_id ? "default" : "secondary"}>{p.accepted_take_id ? "accepted" : "needs review"}</Badge></div><p className="mt-1 text-muted-foreground">{p.expected_text}</p></div>)}</CardContent></Card></div>
  </div></AppShell>;
}
