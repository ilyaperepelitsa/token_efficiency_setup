#!/usr/bin/env python3
"""Read-only tmux indicator; reuse guardian measurements without model calls."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time


def render(project, usable, latest, *, now, guardian):
    prefix = 'CPU guard:' + ('on' if guardian else 'OFF')
    row = latest['projects'][project]
    if not 0 <= now - latest['time'] <= 180:
        return prefix + ' | data:stale'
    if row['available'] != len(usable):
        return prefix + ' | allocation changed'
    holders = [h for h in latest.get('holders', []) if h['project'] == project]
    scopes = 'none' if not holders else 'ok'
    if any(not h.get('cpus') for h in holders):
        scopes = '?'
    if any(set(h.get('cpus', [])) - usable for h in holders):
        scopes = 'VIOLATION'
    value = row.get('cpu_equivalents')
    fresh = 0 <= now - latest.get('measured_at', 0) <= 180
    measured = (fresh and latest.get('seconds', 0) >= 60
        and isinstance(value, (float, int)) and math.isfinite(value) and value >= 0)
    busy = f'~{value:.1f}' if measured else '?'
    suffix = ' partial' if not row.get('complete') else ''
    if not fresh:
        suffix += ' stale'
    if not row.get('active'):
        suffix += ' inactive'
    return f'{prefix} | scopes:{scopes} | {busy}/{len(usable)} cores{suffix}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', type=Path, required=True)
    args = parser.parse_args()
    try:
        import cpu_enforcement as guard
        cfg = guard.load_config()
        project = guard.identify(cfg, info={'cwd': str(args.cwd)})
        if project is None:
            return
        row = guard.reservations.status(cfg['file'])[project]
        latest = json.loads((cfg['runtime'] / 'latest.json').read_text())
        running = subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
            'cpu-reservation-guardian.service'], timeout=1,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        print(render(project, set(row['usable']), latest, now=time.time(), guardian=running))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('CPU status:unknown')


if __name__ == '__main__':
    main()
