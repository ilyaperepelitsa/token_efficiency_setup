#!/usr/bin/env python3
"""Install only this toolkit's files; external packages and MCP config are manual."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = {'claude':'.claude/skills', 'codex':'.agents/skills', 'cursor':'.cursor/skills'}
MARKER = '.managed-by-token-efficiency-setup'


def change_hook(home, script, enabled):
    settings = home/'.claude/settings.json'
    original = settings.read_bytes() if settings.exists() else None
    data = json.loads(original) if original else {}
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise ValueError('Claude settings/hooks must be objects')
    hooks = data.setdefault('hooks', {})
    entries = hooks.get('PostToolUse', [])
    if not isinstance(entries, list):
        raise ValueError('Claude PostToolUse hooks must be a list')
    command = shlex.join([sys.executable, str(script), 'hook', '--provider', 'claude'])
    new_entries = []
    for entry in entries:
        kept = [h for h in entry.get('hooks', []) if str(script) not in h.get('command', '')]
        if kept:
            new_entries.append({**entry, 'hooks':kept})
    if enabled:
        new_entries.append({'matcher':'.*', 'hooks':[{'type':'command',
                            'command':command, 'timeout':15}]})
    if new_entries == entries:
        return
    if not enabled and original is None:
        return
    hooks['PostToolUse'] = new_entries
    settings.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        backups=home/'.local/share/token-efficiency-setup/backups'
        backups.mkdir(parents=True, exist_ok=True)
        name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'.settings.json'
        p=backups/name;p.write_bytes(original);p.chmod(0o600)
    with tempfile.NamedTemporaryFile(mode='w',dir=settings.parent,delete=False) as f:
        json.dump(data,f,indent=2);f.write('\n');temp=Path(f.name)
    os.chmod(temp, settings.stat().st_mode & 0o777 if settings.exists() else 0o600)
    os.replace(temp,settings)


def install(home, clients, claude_hook=False, dry_run=False, remove=False):
    home=Path(home).expanduser().resolve()
    payload=home/'.local/share/token-efficiency-setup/skills/codeburn-review'
    script=payload/'scripts/review.py'
    launcher=home/'.local/bin/codeburn-review'
    links=[home/CLIENTS[client]/'codeburn-review' for client in clients]
    for link in links:
        if link.exists() or link.is_symlink():
            if not link.is_symlink() or link.resolve()!=payload:
                raise ValueError(f'existing skill conflict: {link}')
    if launcher.exists() and str(script) not in launcher.read_text():
        raise ValueError('existing launcher belongs to another installation')
    if payload.exists() and not (payload/MARKER).exists():
        raise ValueError('unmanaged payload directory; refusing overwrite')
    if claude_hook and 'claude' not in clients:
        raise ValueError('--claude-hook requires --clients claude')
    # Parse before file changes so malformed settings cannot leave a partial install.
    settings=home/'.claude/settings.json'
    if (claude_hook or remove) and settings.exists():
        data=json.loads(settings.read_text())
        if not isinstance(data,dict):
            raise ValueError('Claude settings must be an object')
    if dry_run:
        return {'operation':'remove' if remove else 'install', 'clients':clients,
                'claude_hook':claude_hook, 'changes_applied':False}
    if remove:
        for link in links:
            if link.is_symlink() and link.resolve()==payload:
                link.unlink()
        if 'claude' in clients:
            change_hook(home,script,False)
        # Keep launcher if another selected/unselected client still has this skill.
        remaining=any((home/d/'codeburn-review').is_symlink() for d in CLIENTS.values())
        if not remaining and launcher.exists() and str(script) in launcher.read_text():
            launcher.unlink()
        return {'operation':'remove','clients':clients,'payload_retained':True}
    shutil.copytree(ROOT/'skills/codeburn-review',payload,dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (payload/MARKER).touch()
    for link in links:
        link.parent.mkdir(parents=True,exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(payload,target_is_directory=True)
    launcher.parent.mkdir(parents=True,exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec '+shlex.join([sys.executable,str(script)])+' "$@"\n')
    launcher.chmod(0o755)
    if claude_hook:
        change_hook(home,script,True)
    return {'operation':'install','clients':clients,'claude_hook':claude_hook,
            'changes_applied':True}


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clients',nargs='+',choices=list(CLIENTS),required=True)
    p.add_argument('--home',type=Path,default=Path.home(),help='Target home; useful for isolated validation')
    p.add_argument('--claude-hook',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--remove',action='store_true')
    a=p.parse_args()
    print(json.dumps(install(a.home,a.clients,a.claude_hook,a.dry_run,a.remove)))


if __name__=='__main__':
    main()
