#!/usr/bin/env python3
"""Opt-in, isolated Linux native proof; never edit real CPU.md or client settings."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Start and remove one isolated user guardian; run tiny affinity probes')
    args=parser.parse_args()
    if not args.run:
        print('Preview only. --run needs Linux, a user systemd manager, cgroup v2, busctl and >=2 eligible logical CPUs.');return 0
    if not sys.platform.startswith('linux'): raise SystemExit('Linux required')
    eligible=sorted(os.sched_getaffinity(0))
    if len(eligible)<2: raise SystemExit('At least two eligible CPUs required')
    sys.path.insert(0,str(ROOT/'cpu'))
    import cpu_enforcement as guard
    checks={};unit='efficiency-cpu-proof-'+uuid.uuid4().hex[:12]+'.service'
    with tempfile.TemporaryDirectory(prefix='efficiency-native-') as temp:
        directory=Path(temp);project=directory/'project';project.mkdir()
        table=directory/'CPU.md';config=directory/'config.json'
        def reservation(cpu,active=True):
            table.write_text(f'Logical CPUs: {os.cpu_count()}\nSystem reserve: -\nProject CPU limit: {os.cpu_count()}\n'
                '| Project | Count | Reserved | Active | Borrowed |\n| --- | --- | --- | --- | --- |\n'
                f'| example | 1 | {cpu} | {str(active).lower()} | - |\n')
        reservation(eligible[0])
        config.write_text(json.dumps({'file':str(table),'runtime':str(directory/'state'),
            'projects':{'example':{'roots':[str(project)],'unit_prefixes':['example-proof-task-']}}}))
        cfg=guard.load_config(config)
        runner=directory/'cpu-run'
        launcher=shlex.join([sys.executable,str(ROOT/'cpu/cpu_enforcement.py'),
            '--config',str(config),'compact'])
        runner.write_text(f'#!/bin/sh\nexec {launcher} "$@"\n')
        runner.chmod(0o700)
        start=['systemd-run','--user','--collect','--unit='+unit,'-p','Restart=on-failure',
            '-p','MemoryMax=96M','-p','MemorySwapMax=0','-p','TasksMax=64',
            '/usr/bin/flock','-n',str(directory/'guardian.lock'),sys.executable,
            str(ROOT/'cpu/cpu_guardian.py'),'--config',str(config)]
        try:
            subprocess.run(start,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
            body={'hook_event_name':'PreToolUse','tool_name':'Bash','cwd':str(project),'tool_input':{}}
            for index in [0,1]:
                reservation(eligible[index])
                if index == 1:
                    guard.DEFAULT_CONFIG=config
                    cfg.update(compact_commands=True,compact_runner=str(runner))
                other=eligible[1-index]
                code=('import os,json; before=sorted(os.sched_getaffinity(0));\n'
                    f'try: os.sched_setaffinity(0,{{{other}}})\nexcept OSError: pass\n'
                    'print(json.dumps({"before":before,"after":sorted(os.sched_getaffinity(0))}))')
                body['tool_input']['command']=shlex.join([sys.executable,'-c',code])
                wrapped=guard.pre_hook(cfg,body,'claude')['hookSpecificOutput']['updatedInput']['command']
                if index == 1:
                    checks['compact_wrapper_used']=shlex.split(wrapped)[0]==str(runner)
                result=subprocess.run(['/bin/bash','-lc',wrapped],cwd=project,capture_output=True,text=True,timeout=25)
                if result.returncode: raise RuntimeError(result.stderr)
                observed=json.loads(result.stdout)
                checks[f'reservation_{index+1}_exact']=observed['before']==[eligible[index]]
                checks[f'reservation_{index+1}_cannot_expand']=observed['after']==[eligible[index]]
            body['tool_input']['command']="printf '%s\\n' 'literal $HOME'; exit 7"
            wrapped=guard.pre_hook(cfg,body,'claude')['hookSpecificOutput']['updatedInput']['command']
            result=subprocess.run(['/bin/bash','-lc',wrapped],cwd=project,capture_output=True,text=True,timeout=25)
            checks['exit_and_shell_text_preserved']=result.returncode==7 and result.stdout=='literal $HOME\n'
            reservation(eligible[1],False)
            checks['inactive_rejected']=guard.pre_hook(cfg,body,'claude')['hookSpecificOutput']['permissionDecision']=='deny'
        finally:
            # Only the UUID-named proof guardian is stopped. No real workload or
            # client configuration is changed; all submitted commands are tiny.
            subprocess.run(['systemctl','--user','stop',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
            subprocess.run(['systemctl','--user','reset-failed',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    print(json.dumps({'checks':checks,'passed':sum(checks.values()),'total':len(checks),'model_calls':0}))
    return 0 if checks and all(checks.values()) else 1


if __name__=='__main__':sys.exit(main())
