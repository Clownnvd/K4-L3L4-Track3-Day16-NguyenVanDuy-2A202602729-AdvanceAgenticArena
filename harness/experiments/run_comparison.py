"""Run opt-in variants through the unchanged official practice runner.

python -m harness.experiments.run_comparison --variant fragments --out runs/fragments.json
The monkeypatch selects middleware only; scoring, tools, model and traces
remain instructor-owned. No network/API calls are made.
"""

import argparse
from pathlib import Path
import sys

from scripts import run_practice
from harness.experiments.evidence_recovery import FragmentCritic, QueryExpansionRetry, IntentRetrievalRetry
from harness.layers.critic import Critic
from harness.layers.retry import Retry


def build_variant(names, variant, factory=run_practice._student_layers):
    layers = factory(names)
    return [FragmentCritic() if layer.name == 'critic' and variant in ('fragments', 'combined', 'intent')
            else Critic(recover_fragments=False) if layer.name == 'critic'
            else IntentRetrievalRetry() if layer.name == 'retry' and variant == 'intent'
            else QueryExpansionRetry() if layer.name == 'retry' and variant in ('expanded', 'combined')
            else Retry(query_mode='none') if layer.name == 'retry'
            else layer for layer in layers]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=('submitted', 'fragments', 'expanded', 'combined', 'intent'), required=True)
    parser.add_argument('--model', choices=('mock',), default='mock')
    args, remaining = parser.parse_known_args()
    original_factory = run_practice._student_layers
    original_run = run_practice.run_brief

    def recorded_run(*a, **kw):
        result = original_run(*a, **kw)
        path = Path('runs') / 'experiment-traces' / args.variant
        path.mkdir(parents=True, exist_ok=True)
        (path / f'{result.brief_id}.jsonl').write_text(result.trace_jsonl, encoding='utf-8')
        return result

    def factory(names):
        return build_variant(names, args.variant, original_factory)

    run_practice._student_layers = factory
    run_practice.run_brief = recorded_run
    sys.argv = [sys.argv[0], '--model', 'mock', *remaining]
    try:
        return run_practice.main()
    finally:
        run_practice._student_layers = original_factory
        run_practice.run_brief = original_run


if __name__ == '__main__':
    raise SystemExit(main())
