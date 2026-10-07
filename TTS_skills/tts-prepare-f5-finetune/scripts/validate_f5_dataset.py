#!/usr/bin/env python3
import argparse, csv, json, wave
from pathlib import Path

def duration(p):
    if p.suffix.lower()!='.wav': return None
    with wave.open(str(p),'rb') as w: return w.getnframes()/w.getframerate()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('dataset_dir'); a=ap.parse_args(); root=Path(a.dataset_dir); meta=root/'metadata.csv'
    errors=[]; warnings=[]; samples=[]; seen=set(); total=0.0
    if not meta.is_file(): errors.append('metadata.csv missing')
    else:
        with meta.open(encoding='utf-8-sig',newline='') as f:
            rows=csv.reader(f,delimiter='|'); next(rows,None)
            for n,row in enumerate(rows,2):
                if len(row)<2: errors.append(f'line {n}: expected path|text'); continue
                rel,text=row[0].strip(),row[1].strip(); p=root/rel
                if not rel or not text: errors.append(f'line {n}: path and transcript required'); continue
                if rel in seen: errors.append(f'line {n}: duplicate path {rel}')
                seen.add(rel)
                if not p.is_file(): errors.append(f'line {n}: missing {rel}'); continue
                try: d=duration(p)
                except Exception as e: errors.append(f'line {n}: unreadable {rel}: {e}'); continue
                if d is None: warnings.append(f'line {n}: duration not checked for non-WAV {rel}')
                else:
                    if d<=0: errors.append(f'line {n}: empty audio {rel}')
                    if d>30: warnings.append(f'line {n}: long clip {d:.2f}s; consider splitting')
                    total+=d
                samples.append(rel)
    print(json.dumps({'samples':len(samples),'duration_seconds':round(total,3),'errors':errors,'warnings':warnings},indent=2))
    return 1 if errors else 0
if __name__=='__main__': raise SystemExit(main())
