"""Read-only source/evidence map. Never imports an engine or authenticates a run.

Hashes describe files inspected now, not proof of what executed in the past.
Missing historical provenance stays unknown; no data is rewritten or published.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = {
    'v1_and_comparison': {
        'entry': ['simulation.py', 'experiment_runner.py'],
        'conditions_and_agent_io': ['simulation.py'],
        'realization': [],
        'evaluation_and_metrics': ['simulation.py'],
        'display': ['dashboard_v1.html', 'tools/build_ui_previews.py'],
        'saved_patterns': ['simulation_result*.json', 'archive/duplicate-results/simulation_result*.json',
                           'result_*.json', 'summary.json'],
        'gap': 'Action realization is unverified; historical metric inertia is implementation-dependent.',
    },
    'v2': {
        'entry': ['simulation_v2.py'],
        'conditions_and_agent_io': ['simulation_v2.py'],
        'realization': [],
        'evaluation_and_metrics': ['simulation_v2.py'],
        'display': ['dashboard_v2.html', 'tools/build_ui_previews.py'],
        'saved_patterns': ['v2_first_run.json'],
        'gap': 'New runs stopped: independent world-update specification not implemented; F03 remains unresolved.',
    },
    'legacy_eight_state': {
        'entry': ['final_experiment_runner.py', 'simulation_final.py'],
        'conditions_and_agent_io': ['homeostasis_core/gemini_agents.py', 'config/country_types.json',
                                    'scenarios/scenario_01_farmland_missile.json'],
        'realization': ['homeostasis_core/feasibility.py', 'homeostasis_core/gemini_agents.py'],
        'evaluation_and_metrics': ['homeostasis_core/gemini_agents.py', 'homeostasis_core/metrics.py'],
        'display': ['dashboard_final.html'],
        'saved_patterns': ['results/final/*.json', 'results/final/*.checkpoint'],
        'gap': 'Deterministic prototypes and model-tagged artifacts coexist; metadata is not independent execution proof.',
    },
    'v3': {
        'entry': ['tools/run_v3_validation.py', 'tools/check_v3_agent_sdk.py', 'tools/run_v3_live_probe.py'],
        'conditions_and_agent_io': ['homeostasis_v3/autonomous.py', 'homeostasis_v3/agent_adapter.py',
                                    'scenarios/v3/synthetic_baseline.json', 'scenarios/v3/synthetic_network.json'],
        'realization': ['homeostasis_v3/turn.py', 'homeostasis_v3/physical.py', 'homeostasis_v3/settlement.py'],
        'evaluation_and_metrics': ['homeostasis_v3/observation.py', 'homeostasis_v3/metric_definitions.py'],
        'display': ['dashboard_v3.html', 'tools/build_v3_validation.py', 'tools/build_v3_earth.py'],
        'saved_patterns': ['ui/v3/validation/evidence.json', 'ui/v3/validation/manifest.json', 'ui/v3/validation/view.json'],
        'gap': 'Saved validation fixtures are not autonomous Agent research; live probe is not a formal experiment.',
    },
}


def describe_file(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe evidence path')
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        raise ValueError('symlink evidence rejected')
    raw = path.read_bytes()
    return {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def build_report(root=ROOT):
    root = Path(root).resolve()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    systems = {}
    for name, spec in SYSTEMS.items():
        stages = {stage: [describe_file(root, p) for p in spec[stage]]
                  for stage in ('entry', 'conditions_and_agent_io', 'realization', 'evaluation_and_metrics', 'display')}
        paths = sorted({p.relative_to(root).as_posix() for pattern in spec['saved_patterns'] for p in root.glob(pattern)})
        systems[name] = {'current_source_stages': stages,
                         'saved_files': [describe_file(root, p) for p in paths],
                         'historical_execution_source_match': 'not_verified_by_this_report',
                         'gap': spec['gap']}
    return {'schema_version': 1, 'artifact_class': 'read_only_provenance_inventory',
            'checkout_revision': revision, 'hash_basis': 'current_file_bytes_not_commit_equivalence',
            'research_eligible': False, 'publication_performed': False,
            'historical_provenance_reconstructed': False,
            'scope': 'repository file-level map; not a complete run receipt or independent design approval',
            'registry_evidence': [describe_file(root, p) for p in (
                'research/experiments/registry.json', 'research/experiments/artifact_allowlist.json',
                'research/experiments/inventory.json')],
            'systems': systems}


if __name__ == '__main__':
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
