#!/usr/bin/env python3
"""
Controller-specific diagnostics for the DEV-scale adaptive/planned_multisearch runs.
Reads only already-saved artifacts (runs/dev_scale/*/runs.jsonl, results/dev_scale/evaluate/
per_scenario.jsonl, judgments/dev_scale/pointwise/qrels_silver.jsonl) -- no new model calls.

Per scenario x system (adaptive, planned_multisearch): retrieval operations, planned subqueries,
validation errors (type + stage), stop_reason, execution_status, elapsed_seconds, and an
"intervention success" check -- did any operation after the first add a new chunk, not present
in operation 1's assembled bundle, that the pooled judge graded >=2? This distinguishes a
controller that is doing useful additional work from one that is just spending budget.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(p):
    return [json.loads(l) for l in open(p)] if Path(p).exists() else []


def build(scope, runs_dir, qrels_path, per_scenario_path, static_system='legal_static'):
    qrels = {(q['scenario_id'], q['chunk_id']): q for q in load_jsonl(qrels_path)}
    per_scenario = load_jsonl(per_scenario_path)
    coverage = {(r['scenario_id'], r['system']): r['requirement_coverage'] for r in per_scenario}

    rows = []
    for system in ('planned_multisearch', 'adaptive'):
        runs = load_jsonl(ROOT / f'{runs_dir}/{system}/runs.jsonl')
        for r in runs:
            sid = r['scenario_id']
            trace = r.get('trace', [])
            errors = r.get('errors', [])
            error_types = sorted({e['error'] for e in errors})
            planned_subqueries = len(r.get('plan', {}).get('queries', []))

            op1_ids = {e['chunk_id'] for e in trace[0]['bundle']} if trace else set()
            final_ids = {e['chunk_id'] for e in r['ranking']}
            new_after_op1 = final_ids - op1_ids
            new_grade2_after_op1 = [
                cid for cid in new_after_op1
                if (qrels.get((sid, cid)) or {}).get('relevance_grade', 0) is not None
                and (qrels.get((sid, cid)) or {}).get('relevance_grade', 0) >= 2
            ]
            intervention_added_value = bool(new_grade2_after_op1) if len(trace) > 1 else None

            static_cov = coverage.get((sid, 'legal_static'))
            own_cov = coverage.get((sid, system))
            regression_vs_legal_static = (
                own_cov is not None and static_cov is not None and own_cov < static_cov
            )

            rows.append({
                'scope': scope, 'scenario_id': sid, 'system': system,
                'retrieval_operations': r.get('retrieval_operations'),
                'planned_subqueries': planned_subqueries,
                'trace_length': len(trace),
                'n_errors': len(errors), 'error_types': ';'.join(error_types),
                'stop_reason': r.get('stop_reason'), 'execution_status': r.get('execution_status'),
                'elapsed_seconds': round(r.get('elapsed_seconds', 0), 2),
                'n_new_chunks_after_op1': len(new_after_op1),
                'n_new_grade_ge2_after_op1': len(new_grade2_after_op1),
                'intervention_added_grade_ge2_value': intervention_added_value,
                'requirement_coverage': own_cov,
                'legal_static_requirement_coverage': static_cov,
                'regression_vs_legal_static': regression_vs_legal_static,
            })
    return rows


def main():
    rows = build('matched_dev', 'runs/dev_scale', ROOT / 'judgments/dev_scale/pointwise/qrels_silver.jsonl',
                 ROOT / 'results/dev_scale/evaluate/per_scenario.jsonl')
    rows += build('matched_test_frozen', 'runs/test_final', ROOT / 'judgments/test_final/pointwise/qrels_silver.jsonl',
                  ROOT / 'results/test_final/evaluate/per_scenario.jsonl')

    out_path = ROOT / 'results/final/CONTROLLER_DIAGNOSTICS.csv'
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Summary stats
    for scope in ('matched_dev', 'matched_test_frozen'):
        for system in ('planned_multisearch', 'adaptive'):
            sub = [r for r in rows if r['system'] == system and r['scope'] == scope]
            n = len(sub)
            n_fallback = sum(1 for r in sub if r['execution_status'] == 'COMPLETED_WITH_FALLBACKS')
            n_multi_op = [r for r in sub if r['trace_length'] > 1]
            n_intervention_checked = [r for r in n_multi_op if r['intervention_added_grade_ge2_value'] is not None]
            n_intervention_success = [r for r in n_intervention_checked if r['intervention_added_grade_ge2_value']]
            n_regression = [r for r in sub if r['regression_vs_legal_static']]
            print(f'--- {scope} / {system} ---')
            print(f'  n_scenarios={n}, fallback_rate={n_fallback}/{n}={n_fallback/n:.3f}')
            print(f'  multi-operation scenarios: {len(n_multi_op)}/{n}')
            print(f'  intervention added new grade>=2 evidence: {len(n_intervention_success)}/{len(n_intervention_checked)} '
                  f'of multi-op scenarios checked')
            print(f'  regressions vs legal_static (lower coverage): {len(n_regression)}/{n}: '
                  f'{[r["scenario_id"] for r in n_regression]}')
            print()

    print(f'Written {len(rows)} rows to {out_path}')


if __name__ == '__main__':
    main()
