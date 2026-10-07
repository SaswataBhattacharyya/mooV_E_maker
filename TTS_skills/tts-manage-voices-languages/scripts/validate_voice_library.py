#!/usr/bin/env python3
import argparse, json
from pathlib import Path
AUDIO={'.wav','.flac','.mp3','.ogg','.m4a','.aac'}

def alias(line):
    if '=' in line:
        a,r=line.split('=',1); p=[x.strip() for x in r.split(',',1)]; return a.strip(),p[0],p[1] if len(p)>1 else None
    p=[x.strip() for x in line.split('\t') if x.strip()]; return (p+[None])[:3] if len(p)>=2 else (None,None,None)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('voice_dir'); a=ap.parse_args(); root=Path(a.voice_dir)
    errors=[]; warnings=[]; stems={}
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in AUDIO:
            key=p.stem.lower(); stems.setdefault(key,[]).append(str(p))
            ref=p.with_name(p.stem+'.reference.txt'); txt=p.with_suffix('.txt')
            chosen=ref if ref.is_file() else txt if txt.is_file() else None
            if not chosen: warnings.append(f'{p}: no .reference.txt or .txt transcript')
            elif not chosen.read_text(encoding='utf-8-sig').strip(): errors.append(f'{chosen}: empty transcript')
    amap=root/'#character_alias_map.txt'
    aliases=0
    if amap.is_file():
        for n,line in enumerate(amap.read_text(encoding='utf-8-sig').splitlines(),1):
            line=line.strip()
            if not line or line.startswith('#'): continue
            al,target,lang=alias(line); aliases+=1
            if not al or not target: errors.append(f'alias line {n}: invalid format')
            elif target.lower() not in stems: errors.append(f'alias line {n}: target {target!r} has no audio stem')
            if lang and not all(c.isalpha() or c in '-_' for c in lang): errors.append(f'alias line {n}: invalid language {lang!r}')
    dup={k:v for k,v in stems.items() if len(v)>1}
    for k,v in dup.items(): warnings.append(f'duplicate character stem {k!r}: {v}')
    print(json.dumps({'voices':sum(map(len,stems.values())),'aliases':aliases,'errors':errors,'warnings':warnings},indent=2))
    return 1 if errors else 0
if __name__=='__main__': raise SystemExit(main())
