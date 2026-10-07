"""Reopen one exact provider-failed video review; never submit/render media.

Run with the normal API stopped. A quality block is deliberately not retryable.
The next normal worker review uses the same canonical take and output bytes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from story_builder.services.production_ledger import ProductionLedger
from story_builder.scripts.retry_durable_text_stage import _require_api_stopped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--take', required=True)
    parser.add_argument('--review', required=True, help='Exact saved provider-failed review ID')
    parser.add_argument('--api-port', type=int, default=3010)
    parser.add_argument('--retry', action='store_true', help='Explicitly reopen; default only inspects')
    args = parser.parse_args()
    if not args.ledger.is_file():
        parser.error('The existing ledger must exist; no fresh acceptance run will be created.')
    _require_api_stopped(args.api_port)
    ledger = ProductionLedger(args.ledger)
    run = ledger.get_run(project_id=args.project, run_id=args.run)
    take = next((item for item in run['takes'] if item['take_id'] == args.take), None)
    if take is None:
        parser.error('The exact take is absent from this project/run.')
    review = take.get('director_review') or {}
    if review.get('review_id') != args.review:
        parser.error('The exact review is no longer current.')
    if args.retry:
        result = ledger.retry_unavailable_director_video_review(project_id=args.project,
            run_id=args.run, take_id=args.take, review_id=args.review)
    else:
        result = {'take_id': take['take_id'], 'take_status': take['status'],
            'review_id': args.review, 'resolution_status': review.get('resolution_status'),
            'review_action': (review.get('decision') or {}).get('action'),
            'changed': False, 'render_resubmitted': False}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
