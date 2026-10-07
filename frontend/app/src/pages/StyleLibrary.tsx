import { useCallback, useEffect, useState } from "react";
import { Archive, ChevronDown, FilePlus2, GitFork, Loader2, Save, Sparkles, Upload } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const API = import.meta.env.VITE_API_BASE || "/api";
const bases = ["story_film", "social_profile", "corporate_pitch", "informative", "news_report", "advertisement"];
const baseLabel: Record<string, string> = { story_film: "Story / film", social_profile: "Social / short-form", corporate_pitch: "Corporate pitch", informative: "Informative / educational", news_report: "News / reporting", advertisement: "Advertisement" };
async function requestJson(url: string, init?: RequestInit) {
  const response = await fetch(`${API}${url}`, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || `Request failed (${response.status}).`);
  }
  return response.json();
}

export default function StyleLibrary() {
  const [sources, setSources] = useState<any[]>([]);
  const [drafts, setDrafts] = useState<any[]>([]);
  const [variants, setVariants] = useState<any[]>([]);
  const [baseStyle, setBaseStyle] = useState("story_film");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [proposal, setProposal] = useState<any>(null);
  const [proposalText, setProposalText] = useState("");
  const [activeDraft, setActiveDraft] = useState<any>(null);
  const [draftText, setDraftText] = useState("");
  const [history, setHistory] = useState<Record<string, any[]>>({});
  const [busy, setBusy] = useState("");
  const draftDirty = Boolean(activeDraft) && draftText !== JSON.stringify(activeDraft, null, 2);

  const reload = useCallback(async () => {
    const [sourceData, draftData, variantData] = await Promise.all([
      requestJson("/production/v2/style-sources"), requestJson("/production/v2/styles/drafts"),
      requestJson("/production/v2/styles/variants?include_archived=true"),
    ]);
    setSources(sourceData.sources || []); setDrafts(draftData.drafts || []); setVariants(variantData.variants || []);
  }, []);
  useEffect(() => { reload().catch((error) => toast.error(error.message)); }, [reload]);

  const uploadSource = async (file?: File) => {
    if (!file) return;
    setBusy("upload");
    try {
      const form = new FormData(); form.append("file", file);
      const source = await requestJson("/production/v2/style-sources", { method: "POST", body: form });
      await reload(); setSelectedSources((current) => current.includes(source.source_id) ? current : [...current, source.source_id]);
      toast.success(`Added ${source.filename}; text extraction is ready for review.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Source upload failed."); }
    finally { setBusy(""); }
  };

  const analyze = async () => {
    setBusy("analyze"); setProposal(null);
    try {
      const result = await requestJson("/production/v2/styles/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ base_style_id: baseStyle, source_ids: selectedSources }) });
      setProposal(result); setProposalText(JSON.stringify(result.payload, null, 2));
    } catch (error) { toast.error(error instanceof Error ? error.message : "Style analysis failed."); }
    finally { setBusy(""); }
  };

  const createDraft = async () => {
    setBusy("create-draft");
    try {
      const payload = JSON.parse(proposalText);
      const draft = await requestJson("/production/v2/styles/drafts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setActiveDraft(draft); setDraftText(JSON.stringify(draft, null, 2)); setProposal(null); await reload();
      toast.success("Unpublished style draft created. Nothing is active until you publish it.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not create a draft; check the JSON and evidence."); }
    finally { setBusy(""); }
  };

  const openDraft = (draft: any) => { setActiveDraft(draft); setDraftText(JSON.stringify(draft, null, 2)); };
  const saveDraft = async () => {
    if (!activeDraft) return;
    setBusy("save-draft");
    try {
      const edited = JSON.parse(draftText);
      const saved = await requestJson(`/production/v2/styles/drafts/${encodeURIComponent(activeDraft.variant_id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...edited, expected_revision: activeDraft.draft_revision }) });
      setActiveDraft(saved); setDraftText(JSON.stringify(saved, null, 2)); await reload(); toast.success("Draft saved as a new draft revision.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Draft save failed; reload if another edit was made."); }
    finally { setBusy(""); }
  };
  const publishDraft = async () => {
    if (!activeDraft) return;
    setBusy("publish");
    try {
      const published = await requestJson(`/production/v2/styles/drafts/${encodeURIComponent(activeDraft.variant_id)}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: activeDraft.draft_revision }) });
      setActiveDraft(null); setDraftText(""); await reload(); toast.success(`${published.display_name} v${published.version} is now published and immutable.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Publish failed; refresh the draft before retrying."); }
    finally { setBusy(""); }
  };
  const fork = async (variant: any) => {
    setBusy(`fork:${variant.variant_id}`);
    try { const draft = await requestJson(`/production/v2/styles/${encodeURIComponent(variant.variant_id)}/fork`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: variant.version }) }); setActiveDraft(draft); setDraftText(JSON.stringify(draft, null, 2)); await reload(); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not fork this version."); }
    finally { setBusy(""); }
  };
  const archive = async (variant: any) => {
    setBusy(`archive:${variant.variant_id}`);
    try { await requestJson(`/production/v2/styles/${encodeURIComponent(variant.variant_id)}/archive`, { method: "POST" }); await reload(); toast.success("Variant archived. Existing run snapshots are unchanged."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Archive failed."); }
    finally { setBusy(""); }
  };
  const loadHistory = async (variant: any) => {
    if (history[variant.variant_id]) { setHistory((current) => ({ ...current, [variant.variant_id]: [] })); return; }
    try { const result = await requestJson(`/production/v2/styles/${encodeURIComponent(variant.variant_id)}/versions`); setHistory((current) => ({ ...current, [variant.variant_id]: result.versions || [] })); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not load version history."); }
  };

  return <AppShell><div className="space-y-6">
    <div><p className="text-sm font-medium text-primary">Production · governance</p><h1 className="mt-1 text-3xl font-semibold">Narrative Style Library</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Upload a writing reference, inspect its extracted evidence, review a proposed style variant, and publish a version. Published variants are immutable and only affect new runs.</p></div>
    <Card><CardHeader><CardTitle>1 · Add text sources</CardTitle><CardDescription>PDF, Markdown, and TXT only. Sources provide writing guidance—not plot, characters, visual references, or voice identity.</CardDescription></CardHeader><CardContent className="space-y-4">
      <Label htmlFor="style-source-upload" className="inline-flex cursor-pointer items-center rounded-md border px-3 py-2 text-sm hover:bg-muted"><Upload className="mr-2 h-4 w-4" />{busy === "upload" ? "Extracting…" : "Upload PDF / MD / TXT"}</Label><Input id="style-source-upload" type="file" accept=".pdf,.md,.txt,application/pdf,text/plain,text/markdown" className="sr-only" onChange={(event) => { void uploadSource(event.target.files?.[0]); event.currentTarget.value = ""; }} disabled={busy !== ""} />
      {sources.length ? <div className="space-y-2">{sources.map((source) => <label key={source.source_id} className="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm"><input type="checkbox" checked={selectedSources.includes(source.source_id)} onChange={(event) => setSelectedSources((current) => event.target.checked ? [...new Set([...current, source.source_id])] : current.filter((id) => id !== source.source_id))} /><span className="min-w-0"><span className="block font-medium">{source.filename}</span><span className="text-xs text-muted-foreground">{source.source_id} · {source.text_character_count?.toLocaleString()} extracted characters · {source.source_type}</span></span></label>)}</div> : <p className="text-sm text-muted-foreground">No source files yet.</p>}
      <div className="grid gap-3 sm:grid-cols-[minmax(0,18rem)_auto] sm:items-end"><div className="space-y-2"><Label htmlFor="style-base">Base production type</Label><select id="style-base" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={baseStyle} onChange={(event) => setBaseStyle(event.target.value)}>{bases.map((id) => <option key={id} value={id}>{baseLabel[id]}</option>)}</select></div><Button onClick={analyze} disabled={busy !== "" || !selectedSources.length}><Sparkles className="mr-2 h-4 w-4" />{busy === "analyze" ? "Analyzing evidence…" : "Analyze selected sources"}</Button></div>
    </CardContent></Card>

    {proposal ? <Card><CardHeader><CardTitle>2 · Review proposal and evidence</CardTitle><CardDescription>Provider proposal only; it is not stored or active until you create a draft and publish it.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap gap-2"><Badge variant="secondary">{proposal.provider || "configured provider"}</Badge><Badge variant="outline">Evidence hash {proposal.evidence_hash?.slice(0, 12)}</Badge></div><div className="space-y-2">{(proposal.payload?.evidence || []).map((card: any, index: number) => <div key={`${card.source_id}-${card.locator}-${index}`} className="rounded-md border p-3"><div className="flex flex-wrap items-center gap-2"><Badge>{card.kind}</Badge><span className="text-xs text-muted-foreground">{card.locator} · confidence {card.confidence}</span></div><p className="mt-2 text-sm">{card.statement}</p><blockquote className="mt-2 border-l-2 pl-3 text-xs text-muted-foreground">{card.quote}</blockquote></div>)}</div><div className="space-y-2"><Label htmlFor="style-proposal-json">Editable proposal JSON</Label><Textarea id="style-proposal-json" className="min-h-64 font-mono text-xs" value={proposalText} onChange={(event) => setProposalText(event.target.value)} /></div><Button onClick={createDraft} disabled={busy !== ""}><FilePlus2 className="mr-2 h-4 w-4" />Create unpublished draft</Button></CardContent></Card> : null}

    {(drafts.length || activeDraft) ? <Card><CardHeader><CardTitle>3 · Drafts</CardTitle><CardDescription>Draft edits use revision checks. Publish only after reviewing the rules and evidence.</CardDescription></CardHeader><CardContent className="space-y-4">{drafts.map((draft) => <button key={draft.variant_id} onClick={() => openDraft(draft)} className="mr-2 rounded-md border px-3 py-2 text-left text-sm hover:bg-muted"><span className="font-medium">{draft.display_name}</span><span className="ml-2 text-xs text-muted-foreground">{baseLabel[draft.base_style_id]} · draft r{draft.draft_revision}</span></button>)}{activeDraft ? <><div className="flex items-center gap-2"><Badge variant="secondary">Unpublished · revision {activeDraft.draft_revision}</Badge><span className="text-sm font-medium">{activeDraft.display_name}</span></div><Textarea aria-label="Style draft JSON" value={draftText} onChange={(event) => setDraftText(event.target.value)} className="min-h-64 font-mono text-xs" />{draftDirty ? <p role="status" className="text-xs text-amber-700">Unsaved edits: save the draft before publishing.</p> : null}<div className="flex flex-wrap gap-2"><Button variant="outline" onClick={saveDraft} disabled={busy !== "" || !draftDirty}><Save className="mr-2 h-4 w-4" />Save draft edits</Button><Button onClick={publishDraft} disabled={busy !== "" || draftDirty}><CheckIcon />Publish immutable version</Button></div></> : null}</CardContent></Card> : null}

    <Card><CardHeader><CardTitle>Published variants</CardTitle><CardDescription>Versions stay fixed once published. Fork to create the next editable version.</CardDescription></CardHeader><CardContent className="space-y-3">{variants.length ? variants.map((variant) => <div key={variant.variant_id} className="rounded-lg border p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><h3 className="font-medium">{variant.display_name}</h3><Badge variant={variant.status === "archived" ? "secondary" : "default"}>{variant.status}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{baseLabel[variant.base_style_id]} · v{variant.version} · {variant.variant_id}</p></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => loadHistory(variant)}><ChevronDown className="mr-1 h-4 w-4" />Version history</Button><Button size="sm" variant="outline" onClick={() => fork(variant)} disabled={busy !== ""}><GitFork className="mr-1 h-4 w-4" />Fork</Button>{variant.status !== "archived" ? <Button size="sm" variant="outline" onClick={() => archive(variant)} disabled={busy !== ""}><Archive className="mr-1 h-4 w-4" />Archive</Button> : null}</div></div>{history[variant.variant_id]?.length ? <div className="mt-3 space-y-2 border-t pt-3">{history[variant.variant_id].map((version: any) => <div key={version.version} className="rounded bg-muted/50 p-3"><p className="text-sm font-medium">Version {version.version}</p><p className="mt-1 text-xs text-muted-foreground">Published {version.published_at} · hash {version.content_hash?.slice(0, 16)}</p><p className="mt-2 text-xs">{version.example_brief}</p></div>)}</div> : null}</div>) : <p className="text-sm text-muted-foreground">No published style variants.</p>}</CardContent></Card>
    {busy ? <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Working…</div> : null}
  </div></AppShell>;
}

function CheckIcon() { return <span aria-hidden="true" className="mr-2 inline-block">✓</span>; }
