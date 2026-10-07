"""One explicit held-unit repair through the ordinary durable text worker; default dry-run."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--revision-id', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-provider-content-egress', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ['CODEX_REASONING_MODEL'] = 'gpt-6-sol'
    from story_builder.api import main as api
    from story_builder.services import reasoning_provider
    from story_builder.services.production_text_repair import select_held_shot_units
    from story_builder.scripts.retry_durable_text_stage import _require_api_stopped, _ensure_no_image_jobs_or_takes, settled_retry_outcome
    reasoning_provider.DEFAULT_CODEX_MODEL = 'gpt-6-sol'
    store = api._production_stage_task_store()
    tasks = store.list_run(project_id=args.project_id, run_id=args.run_id)
    task = next((row for row in tasks if row['task_id'] == args.task_id), None)
    if not task or task['stage'] != 'text:shot_plans' or task['status'] != 'completed' or (task.get('result') or {}).get('revision_id') != args.revision_id:
        raise ValueError('Expected the exact completed shot-plan task and its saved held revision.')
    if any(row['status'] in {'queued', 'running', 'recovery_required'} for row in tasks):
        raise ValueError('Reconcile active tasks before repair.')
    base = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, args.project_id, args.run_id, 'shot_plans', args.revision_id)
    run = api._production_v2_ledger().get_run(project_id=args.project_id, run_id=args.run_id)
    if run['config'].get('provider') != 'codex' or run['config'].get('control_mode') != 'fully_automated':
        raise ValueError('Expected the saved Full/Codex run.')
    revisions = api.production_story_revisions.list_stage_revisions(api.OUTPUT_ROOT, args.project_id, args.run_id, 'shot_plans')
    if not base or max(revisions, key=lambda row: (row.get('created_at', ''), row['revision_id']))['revision_id'] != args.revision_id:
        raise ValueError('The held revision is not latest.')
    held = select_held_shot_units(base, task['request']['units'])
    if len(held) != 1 or held[0]['unit_id'] != 'shot-001-01':
        raise ValueError('This approved bounded attempt is only for shot-001-01.')
    key = f'held-shot-repair:{args.revision_id}:gpt-6-sol:v1'
    if any(row['idempotency_key'] == key for row in tasks):
        raise ValueError('The one repair key was already used; inspect its result.')
    _require_api_stopped(int(os.environ.get('STORY_BUILDER_BACKEND_PORT', '3010')))
    _ensure_no_image_jobs_or_takes(api, args.project_id, args.run_id)
    request = {**task['request'], 'repair_from_revision_id': args.revision_id, 'max_attempts': 1}
    summary = {'project_id': args.project_id, 'run_id': args.run_id, 'parent_revision_id': args.revision_id,
        'provider': 'codex', 'model': 'gpt-6-sol', 'held_unit_ids': [u['unit_id'] for u in held],
        'controller_advancement': False, 'execute': args.execute, 'idempotency_key': key}
    if not args.execute:
        print(json.dumps({**summary, 'outcome': 'preflight_passed'}, indent=2)); return 0
    if not args.confirm_provider_content_egress:
        raise ValueError('Provider dispatch requires explicit content-egress confirmation.')
    queued = store.enqueue(project_id=args.project_id, run_id=args.run_id, stage='text:shot_plans', idempotency_key=key, request=request)
    print(json.dumps({**summary, 'task_id': queued['task_id'], 'outcome': 'started'}), flush=True)
    api._execute_production_story_stage_task(queued['task_id'], advance_controller=False)
    final = store.get(project_id=args.project_id, run_id=args.run_id, task_id=queued['task_id'])
    revision_id = (final.get('result') or {}).get('revision_id')
    revision = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, args.project_id, args.run_id, 'shot_plans', revision_id) if revision_id else None
    result = {**summary, 'task_id': final['task_id'], 'status': final['status'], 'result': final.get('result'), 'error': final.get('error'),
        **settled_retry_outcome(final, revision, project_id=args.project_id, run_id=args.run_id, model='gpt-6-sol')}
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['outcome'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
