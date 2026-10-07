#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('workflow'); a=ap.parse_args(); d=json.loads(Path(a.workflow).read_text(encoding='utf-8'))
    nodes=d.get('nodes',[]) if isinstance(d,dict) else []
    types=[str(n.get('type','')) for n in nodes]
    pick=lambda words:[{'id':n.get('id'),'type':n.get('type'),'title':n.get('title')} for n in nodes if any(w.lower() in str(n.get('type','')).lower() for w in words)]
    report={'node_count':len(nodes),'engines':pick(['Engine','ChatterBox','F5TTS','IndexTTS','VibeVoice','Higgs']), 'voices':pick(['CharacterVoices','VoiceCapture']), 'srt':pick(['SRT']), 'step_edit':pick(['StepAudioEditXAudioEditor']), 'scene_surgery':pick(['SceneSplitter','SceneEditDriver','SceneConcat']), 'outputs':pick(['PreviewAudio','SaveAudio'])}
    report['generation_only']=bool(report['srt']) and not report['step_edit'] and not report['scene_surgery']
    print(json.dumps(report,indent=2,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
