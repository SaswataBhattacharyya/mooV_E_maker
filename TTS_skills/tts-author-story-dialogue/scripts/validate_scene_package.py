#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path

EMOTIONS=set('happy sad angry excited calm fearful surprised disgusted confusion empathy embarrass depressed coldness admiration remove'.split())
STYLES=set('whisper serious child older girl pure sister sweet exaggerated ethereal generous recite act_coy warm shy comfort authority chat radio soulful gentle story vivid program news advertising roar murmur shout deeply loudly arrogant friendly remove'.split())
SPEEDS={'faster','slower','more faster','more slower','more_faster','more_slower'}
TYPES={'emotion','style','speed','paralinguistic','denoise','vad','voice'}
STAMP=re.compile(r'^(\d\d):(\d\d):(\d\d),(\d{3})$')

def seconds(s):
    m=STAMP.match(s.strip())
    if not m: raise ValueError(f'invalid timestamp {s!r}')
    h,mi,se,ms=map(int,m.groups()); return h*3600+mi*60+se+ms/1000

def parse_srt(path):
    blocks=re.split(r'\n\s*\n',Path(path).read_text(encoding='utf-8-sig').strip())
    out=[]
    for b in blocks:
        lines=[x.rstrip() for x in b.splitlines() if x.strip()]
        ti=next((i for i,x in enumerate(lines) if '-->' in x),None)
        if ti is None: raise ValueError(f'SRT block lacks timing: {b[:60]!r}')
        a,z=[x.strip() for x in lines[ti].split('-->',1)]
        out.append((seconds(a),seconds(z),'\n'.join(lines[ti+1:])))
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--srt',required=True); ap.add_argument('--edits',required=True); a=ap.parse_args()
    errors=[]
    try: subs=parse_srt(a.srt)
    except Exception as e: errors.append(str(e)); subs=[]
    last=0.0
    for i,(s,e,t) in enumerate(subs,1):
        if e<=s: errors.append(f'subtitle {i}: end must exceed start')
        if s<last: errors.append(f'subtitle {i}: overlaps previous subtitle')
        if not t.strip(): errors.append(f'subtitle {i}: empty text')
        last=e
    try:
        raw=json.loads(Path(a.edits).read_text(encoding='utf-8')); edits=raw.get('edits',[]) if isinstance(raw,dict) else raw
        if not isinstance(edits,list): raise ValueError('edit JSON must be a list or {"edits": [...]}')
    except Exception as e: errors.append(str(e)); edits=[]
    last=0.0
    for i,x in enumerate(sorted(edits,key=lambda q:float(q.get('start',-1))),1):
        try: s=float(x['start']); e=float(x['end'])
        except Exception: errors.append(f'edit {i}: numeric start/end required'); continue
        if s<0 or e<=s: errors.append(f'edit {i}: invalid range {s}->{e}')
        if s<last: errors.append(f'edit {i}: overlaps previous edit')
        if subs and e>subs[-1][1]+1e-6: errors.append(f'edit {i}: exceeds SRT duration')
        typ=str(x.get('edit_type','')).lower()
        if typ not in TYPES: errors.append(f'edit {i}: unsupported edit_type {typ!r}')
        val={'emotion':x.get('emotion'),'style':x.get('style'),'speed':x.get('speed')}.get(typ)
        allowed={'emotion':EMOTIONS,'style':STYLES,'speed':SPEEDS}.get(typ)
        if allowed is not None and str(val).lower() not in allowed: errors.append(f'edit {i}: unsupported {typ} {val!r}')
        try: it=int(x.get('n_edit_iterations',x.get('iterations',1)))
        except Exception: it=0
        if not 1<=it<=5: errors.append(f'edit {i}: iterations must be 1..5')
        if 'file_name' in x: errors.append(f'edit {i}: file_name is splitter output, not source input')
        last=e
    print(json.dumps({'subtitles':len(subs),'edits':len(edits),'errors':errors},indent=2))
    return 1 if errors else 0
if __name__=='__main__': raise SystemExit(main())
