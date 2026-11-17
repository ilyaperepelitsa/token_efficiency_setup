#!/usr/bin/env python3
"""Explicitly opt into Linux CPU enforcement; preview by default, never edit AGENTS."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:
    import tomllib
except ImportError:
    tomllib=None

ROOT=Path(__file__).resolve().parents[1]
MARKER='token-efficiency-setup:cpu'
BEGIN='# '+MARKER+':start'
END='# '+MARKER+':end'
UNIT='cpu-reservation-guardian.service'


def module():
    directory=ROOT/'cpu'
    spec=importlib.util.spec_from_file_location('cpu_installer_policy',directory/'cpu_enforcement.py')
    m=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(directory))
    try: spec.loader.exec_module(m)
    finally: sys.path.pop(0)
    return m


def hook_command(script,config,provider):
    return shlex.join([sys.executable,str(script),'--config',str(config),'hook','--provider',provider])


def claude_settings(text,command,remove=False):
    data=json.loads(text or '{}');hooks=data.setdefault('hooks',{})
    if not isinstance(hooks,dict): raise ValueError('Claude hooks must be an object')
    for event in ['PreToolUse','PostToolUse','Stop']:
        groups=hooks.setdefault(event,[])
        remaining=[]
        for group in groups:
            kept=[h for h in group.get('hooks',[]) if h.get('command')!=command]
            if kept: remaining.append({**group,'hooks':kept})
        # Concurrent input rewriters are not safely composable without an adapter.
        if event=='PreToolUse' and not remove:
            for group in remaining:
                try: matches=re.search(group.get('matcher','.*'),'Bash') is not None
                except re.error: raise ValueError('invalid existing PreToolUse matcher')
                if matches: raise ValueError('existing Bash PreToolUse hook: integrate explicitly; refusing concurrent rewrites')
        if not remove:
            group={'hooks':[{'type':'command','command':command,'timeout':15}]}
            if event=='PreToolUse': group['matcher']='^Bash$';group['hooks'][0]['onFailure']='block'
            remaining.append(group)
        hooks[event]=remaining
    return json.dumps(data,indent=2)+'\n'


def codex_settings(text,command,remove=False):
    if tomllib is None: raise ValueError('Codex CPU configuration requires Python 3.11+; no settings changed')
    tomllib.loads(text)
    if BEGIN in text:
        before,tail=text.split(BEGIN,1);_,after=tail.split(END,1);text=before+after
    if not remove:
        existing=tomllib.loads(text).get('hooks',{}).get('PreToolUse',[])
        if existing: raise ValueError('existing Codex PreToolUse hooks: integrate explicitly; refusing concurrent rewrites')
        block=[BEGIN]
        for event in ['PreToolUse','PostToolUse','Stop']:
            block.append(f'[[hooks.{event}]]')
            if event=='PreToolUse': block.append('matcher = "Bash"')
            block += [f'[[hooks.{event}.hooks]]','type = "command"','command = '+json.dumps(command),'timeout = 15']
        block.append(END)
        text=text.rstrip()+'\n\n'+'\n'.join(block)+'\n'
    tomllib.loads(text)
    return text


def unit_arg(value):
    return shlex.quote(str(value).replace('%','%%').replace('$','$$'))


def prepare(home,config_path,clients,remove=False):
    home=Path(home).expanduser().resolve();policy=module()
    cfg=policy.load_config(config_path)
    if not remove:
        rows=policy.reservations.status(cfg['file'])
        if set(rows)!=set(cfg['projects']): raise ValueError('register every CPU.md project in the configuration')
    payload=home/'.local/share/token-efficiency-setup/cpu'
    if payload.exists() and not (payload/('.'+MARKER)).is_file(): raise ValueError('unmanaged CPU payload; refusing overwrite')
    if remove and not (payload/('.'+MARKER)).is_file(): raise ValueError('no managed CPU installation to remove')
    config=home/'.config/cpu-reservations/config.json'
    runtime=home/'.cache/cpu-reservations'
    normalized={'file':str(cfg['file']),'runtime':str(runtime),'projects':cfg['projects']}
    seen_roots=[]
    for name,project in normalized['projects'].items():
        project['roots']=[str(Path(r).expanduser().resolve()) for r in project['roots']]
        for root in project['roots']:
            if any(owner!=name and (policy.in_root(root,r) or policy.in_root(r,root)) for owner,r in seen_roots):
                raise ValueError('worktree roots overlap across projects')
            seen_roots.append((name,root))
    prefixes=[]
    for project in cfg['projects'].values():
        for prefix in project['unit_prefixes']:
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*-',prefix): raise ValueError('safe dashed service prefix required')
            if UNIT.startswith(prefix) or prefix in {'app-','systemd-','user-','session-','dbus-'}:
                raise ValueError('reserved/broad system service prefix')
            if any(prefix.startswith(p) or p.startswith(prefix) for p in prefixes): raise ValueError('overlapping service prefixes')
            prefixes.append(prefix)
    files={}
    if remove:
        for other,path in [('claude',home/'.claude/settings.json'),('codex',home/'.codex/config.toml')]:
            if other not in clients and path.exists() and 'token-efficiency-setup/cpu/cpu_enforcement.py' in path.read_text():
                raise ValueError('another client still uses the guardian; remove all installed CPU clients together')
    for client in clients:
        if client=='claude':
            path=home/'.claude/settings.json'
            text=path.read_text() if path.exists() else '{}'
            files[path]=claude_settings(text,hook_command(payload/'cpu_enforcement.py',config,client),remove)
        else:
            path=home/'.codex/config.toml'
            hooks_json=home/'.codex/hooks.json'
            if hooks_json.exists() and not remove: raise ValueError('existing Codex hooks.json: use one hook format per layer')
            files[path]=codex_settings(path.read_text() if path.exists() else '',
                hook_command(payload/'cpu_enforcement.py',config,client),remove)
    service=home/'.config/systemd/user'/UNIT
    for prefix in prefixes:
        path=home/'.config/systemd/user'/(prefix+'.service.d')/'50-token-efficiency-cpu.conf'
        files[path]='# '+MARKER+'\n[Service]\nExecCondition='+shlex.join([sys.executable])+ ' '+unit_arg(payload/'cpu_enforcement.py')+' --config '+unit_arg(config)+' admit --unit %n\n'
    template=(ROOT/'cpu/templates/guardian.service.in').read_text()
    for key,value in {'LOCK':runtime/'guardian.lock','PYTHON':sys.executable,
                      'GUARDIAN':payload/'cpu_guardian.py','CONFIG':config}.items():
        template=template.replace('@'+key+'@',unit_arg(value))
    files[service]='# '+MARKER+'\n'+template
    launcher=home/'.local/bin/cpu-enforce'
    files[launcher]='# '+MARKER+'\nexec '+shlex.join([sys.executable,str(payload/'cpu_enforcement.py'),'--config',str(config)])+' "$@"\n'
    files[launcher]='#!/bin/sh\n'+files[launcher]
    compact=home/'.local/bin/cpu-run'
    if not remove or (compact.is_file() and MARKER in compact.read_text()):
        files[compact]=files[launcher].replace(' "$@"', ' compact "$@"')
    for path in [service,launcher,*[p for p in files if p==compact or p.name=='50-token-efficiency-cpu.conf']]:
        if path.exists() and MARKER not in path.read_text(): raise ValueError('unmanaged CPU file conflict; preserve existing installation')
    if config.exists() and not payload.exists() and config.resolve()!=Path(config_path).resolve():
        raise ValueError('existing CPU installation; manual migration required')
    return {'home':home,'payload':payload,'config':config,'runtime':runtime,'files':files,
            'normalized':normalized,'service':service,'launcher':launcher,'compact':compact,'clients':clients}


def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text()==text: return
    if path.exists():
        folder=path.parent/'token-efficiency-cpu-backups';folder.mkdir(exist_ok=True)
        backup=folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+path.name)
        backup.write_bytes(path.read_bytes());backup.chmod(0o600)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.cpu-')
    try:
        with os.fdopen(fd,'w') as stream: stream.write(text)
        os.chmod(temp,0o600);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def install(plan,apply=False,remove=False):
    if not apply: return {'operation':'remove' if remove else 'install','applied':False,'clients':plan['clients'],
        'targets':[str(p) for p in plan['files']],'cpu_table_modified':False}
    if not sys.platform.startswith('linux'): raise ValueError('CPU enforcement requires Linux/systemd')
    if remove:
        subprocess.run(['systemctl','--user','disable','--now',UNIT],check=True)
        for path,text in plan['files'].items():
            if path.name in {'settings.json','config.toml'}: write(path,text)
            elif path.exists() and MARKER in path.read_text(): path.unlink()
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        return {'operation':'remove','applied':True,'payload_retained':True}
    # Validate everything above before mutation; install no external dependencies.
    active=subprocess.run(['systemctl','--user','is-active','--quiet',UNIT],capture_output=True).returncode==0
    changed=any(not (plan['payload']/s.name).exists() or (plan['payload']/s.name).read_text()!=s.read_text()
        for s in (ROOT/'cpu').glob('*.py'))
    plan['payload'].mkdir(parents=True,exist_ok=True)
    for source in (ROOT/'cpu').glob('*.py'): write(plan['payload']/source.name,source.read_text())
    (plan['payload']/('.'+MARKER)).touch()
    plan['runtime'].mkdir(parents=True,exist_ok=True)
    write(plan['config'],json.dumps(plan['normalized'],indent=2)+'\n')
    roots=[r for p in plan['normalized']['projects'].values() for r in p['roots']]
    write(plan['config'].with_name('roots.json'),json.dumps(roots)+'\n')
    # Activate the resource controller before enabling shell rewrites.
    for path,text in plan['files'].items():
        if path.name not in {'settings.json','config.toml'}: write(path,text)
    plan['launcher'].chmod(0o700)
    plan['compact'].chmod(0o700)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now',UNIT],check=True)
    if active and changed: subprocess.run(['systemctl','--user','restart',UNIT],check=True)
    subprocess.run(['systemctl','--user','is-active','--quiet',UNIT],check=True)
    normalized={**plan['normalized'],'compact_commands':True,'compact_runner':str(plan['compact'])}
    write(plan['config'],json.dumps(normalized,indent=2)+'\n')
    for path,text in plan['files'].items():
        if path.name in {'settings.json','config.toml'}: write(path,text)
    return {'operation':'install','applied':True,'clients':plan['clients'],'guardian_active':True,
            'native_hook_trust_and_real_client_probe_still_required':True}


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path,help='Private config pointing at your CPU.md; never commit it')
    p.add_argument('--home',type=Path,default=Path.home())
    p.add_argument('--clients',nargs='+',choices=['claude','codex'],required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--remove',action='store_true')
    args=p.parse_args()
    try: print(json.dumps(install(prepare(args.home,args.config,args.clients,args.remove),args.apply,args.remove)))
    except (ValueError,OSError,subprocess.SubprocessError) as exc: p.exit(1,str(exc)+'\n')


if __name__=='__main__': main()
