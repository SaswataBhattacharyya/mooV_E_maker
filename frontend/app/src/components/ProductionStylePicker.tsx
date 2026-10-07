import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Label } from "@/components/ui/label";

const API = import.meta.env.VITE_API_BASE || "/api";
const fallbackBases = [
  ["story_film", "Story / film"], ["social_profile", "Social / short-form"],
  ["corporate_pitch", "Corporate pitch"], ["informative", "Informative / educational"],
  ["news_report", "News / reporting"], ["advertisement", "Advertisement"],
];

type Props = {
  value: string;
  variantId?: string;
  onChange: (productionType: string, variantId: string) => void;
  disabled?: boolean;
  title?: string;
  showManageLink?: boolean;
};

export function ProductionStylePicker({ value, variantId = "", onChange, disabled = false, title = "Production style", showManageLink = true }: Props) {
  const [catalog, setCatalog] = useState<any>(null);
  useEffect(() => {
    let active = true;
    fetch(`${API}/production/v2/styles`).then((response) => response.ok ? response.json() : Promise.reject(new Error("Style catalog unavailable")))
      .then((data) => { if (active) setCatalog(data); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  const productionTypes = useMemo(() => catalog?.production_types?.length
    ? catalog.production_types.map((item: any) => [item.production_type, item.display_name] as [string, string])
    : fallbackBases, [catalog]);
  const selectedBase = catalog?.production_types?.find((item: any) => item.production_type === value);
  const variants = selectedBase?.variants || [];
  return <div className="min-w-0 w-full max-w-[min(100%,calc(100vw-6rem))] space-y-2">
    <Label htmlFor={`production-style-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>{title}</Label>
    <div className="grid min-w-0 w-full gap-2 sm:grid-cols-2">
      <select aria-label="Production type" id={`production-style-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} className="h-10 min-w-0 max-w-full rounded-md border border-input bg-background px-3 text-sm" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value, "")}>
        {productionTypes.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <select aria-label="Narrative variant" className="h-10 min-w-0 max-w-full rounded-md border border-input bg-background px-3 text-sm" value={variantId} disabled={disabled || !variants.length} onChange={(event) => onChange(value, event.target.value)}>
        <option value="">Base default</option>{variants.map((item: any) => <option key={item.variant_id} value={item.variant_id}>{item.display_name} · v{item.version}</option>)}
      </select>
    </div>
    <p className="text-xs text-muted-foreground">{variants.length ? "Published variants refine this production type; the chosen version is frozen in new runs." : "No published variants for this production type; the base style is used."}{showManageLink ? <> <Link className="underline underline-offset-2" to="/style-library">Manage styles</Link></> : null}</p>
  </div>;
}
