"""Run each test module in a fresh process to avoid accumulated Qt GUI state."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.brand-validation'

def run(module):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR='1')
    report = OUTPUT / f'{module.stem}.xml'
    process = subprocess.run([sys.executable, '-m', 'pytest', str(module), '-p', 'no:cacheprovider',
        '--basetemp', str(OUTPUT / 'temp' / module.stem), '--junitxml', str(report)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (OUTPUT / f'{module.stem}.log').write_text(process.stdout + process.stderr, encoding='utf-8')
    return module.name, process.returncode, report

def main():
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / 'temp').mkdir(exist_ok=True)
    failures = []
    totals = dict(tests=0, failures=0, errors=0, skipped=0, xfailed=0)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(run, module) for module in sorted((ROOT / 'tests').glob('test_*.py'))]
        for job in as_completed(jobs):
            name, code, report = job.result()
            print(f'{name}: {"PASS" if code == 0 else "FAIL"}', flush=True)
            if code:
                failures.append(name)
            if report.exists():
                tree = ET.parse(report)
                for case in tree.findall('.//testcase'):
                    totals['tests'] += 1
                    for kind in ('failure', 'error', 'skipped'):
                        node = case.find(kind)
                        if node is not None:
                            key = 'xfailed' if kind == 'skipped' and node.get('type') == 'pytest.xfail' else {'failure':'failures','error':'errors','skipped':'skipped'}[kind]
                            totals[key] += 1
    totals['passed'] = totals['tests'] - sum(totals[k] for k in ('failures','errors','skipped','xfailed'))
    print(totals, flush=True)
    if failures:
        print('Failed modules:', ', '.join(failures), flush=True)
    return bool(failures)

if __name__ == '__main__':
    sys.exit(main())
