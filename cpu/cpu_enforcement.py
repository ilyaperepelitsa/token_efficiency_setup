#!/usr/bin/env python3
"""CPU admission, inherited shell affinity, drain verification and bounded feedback.

This is a same-user reliability guard, not an adversarial security boundary.
CPU.md is the sole reservation authority; runtime files contain current checks only.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = Path.home()/'.config/cpu-reservations/config.json'
spec = importlib.util.spec_from_file_location('cpu_reservations', HERE/'cpu-reservations.py')
reservations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reservations)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.cpu-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, separators=(',', ':'))
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def load_config(path=DEFAULT_CONFIG):
    path = Path(path).expanduser().resolve()
    result = json.loads(path.read_text())
    result['file'] = Path(result['file']).expanduser().resolve()
    result['runtime'] = Path(result.get('runtime', str(Path.home()/'.cache/cpu-reservations'))).expanduser()
    result['config'] = path
    if not isinstance(result['projects'], dict): raise ValueError('projects must be a mapping')
    for name, project in result['projects'].items():
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name): raise ValueError('invalid project name')
        if not project.get('roots') or not project.get('unit_prefixes'):
            raise ValueError('project roots and unit prefixes required')
    return result


@contextlib.contextmanager
def locked(cfg):
    path = cfg['file']
    lock_path=path.with_name(path.name+'.lock')
    try: lock=lock_path.open('r')
    except FileNotFoundError: lock=lock_path.open('a')
    with lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def control(*args):
    command = ['systemctl', '--user', *args]
    if args[:1] == ('list-units',):
        # Recover a stalled read without extending the inventory timeout budget.
        try:
            return subprocess.check_output(command, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            return subprocess.check_output(command, text=True, timeout=5)
    return subprocess.check_output(command, text=True, timeout=10)


def unit_info(unit):
    raw = control('show', unit, '-p', 'WorkingDirectory', '-p', 'ExecStart',
        '-p', 'ControlGroup', '-p', 'ActiveState', '-p', 'InvocationID',
        '-p', 'AllowedCPUs', '-p', 'EffectiveCPUs', '-p', 'CPUUsageNSec')
    return dict(line.split('=',1) for line in raw.splitlines() if '=' in line)


def unit_infos(units):
    if not units: return {}
    raw=control('show',*units,'-p','Id','-p','WorkingDirectory','-p','ExecStart',
        '-p','ControlGroup','-p','ActiveState','-p','InvocationID','-p','AllowedCPUs',
        '-p','EffectiveCPUs','-p','CPUUsageNSec')
    result={}
    for block in raw.strip().split('\n\n'):
        info=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
        if info.get('Id'): result[info['Id']]=info
    return result


def mask(value):
    result = set()
    for part in re.split(r'[,\s]+', value.strip()):
        if not part: continue
        if '-' in part:
            lo, hi = map(int,part.split('-'))
            if lo > hi or hi-lo > 65536: raise ValueError('invalid CPU range')
            result.update(range(lo,hi+1))
        else: result.add(int(part))
    if any(c<0 for c in result): raise ValueError('negative CPU')
    return result


def in_root(value, root):
    try: Path(value).resolve().relative_to(Path(root).resolve()); return True
    except (ValueError, OSError): return False


def identify(cfg, unit='', info=None):
    info = info or {}
    named = [name for name,p in cfg['projects'].items()
        if any(unit.startswith(prefix) for prefix in p['unit_prefixes'])]
    if len(named)>1: raise ValueError('ambiguous project unit prefix')
    if named: return named[0]
    cwd = info.get('WorkingDirectory') or info.get('cwd') or ''
    roots = [name for name,p in cfg['projects'].items()
        if cwd and any(in_root(cwd,r) for r in p['roots'])]
    if len(roots)>1: raise ValueError('ambiguous project worktree')
    if roots: return roots[0]
    command = info.get('ExecStart','')
    found = [name for name,p in cfg['projects'].items()
        if any(re.search(re.escape(str(Path(r).resolve()))+r'(?=/|\s|[;\"\x27]|$)',command)
               for r in p['roots'])]
    if len(found)>1: raise ValueError('ambiguous project executable: set WorkingDirectory')
    return found[0] if found else None


def allowed(cfg, project, effective, requested):
    state = reservations.status(cfg['file'])
    if project not in state: raise ValueError('project missing from CPU.md')
    row = state[project]
    if not row['active']: raise ValueError('project inactive: activate your own row before work')
    usable = set(row['usable'])
    if requested and not requested <= usable:
        raise ValueError('requested CPUs outside current usable reservation: '+','.join(map(str,sorted(requested-usable))))
    selected = (requested or usable) & effective
    if not selected: raise ValueError('no admitted CPUs within effective parent affinity; check outstanding loans')
    # Explicit masks must be honored exactly; never silently move a pinned job.
    if requested and selected != requested: raise ValueError('requested CPUs excluded by effective parent')
    return selected


def process_start(pid):
    try: return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    except (OSError,IndexError): return None


def group_cpus(group):
    root=Path('/sys/fs/cgroup'+group); found=set()
    if not group: return found
    for current in [root, *[p for p in root.rglob('*') if p.is_dir()]]:
        try: pids=(current/'cgroup.procs').read_text().split()
        except OSError: continue
        for pid in pids:
            try: found.update(os.sched_getaffinity(int(pid)))
            except (OSError,ValueError): pass
    return found


def queued_jobs(raw):
    if raw.lstrip().startswith('['): return json.loads(raw)
    rows=[]
    for line in raw.splitlines():
        cells=line.split()
        if len(cells)==4 and cells[0].isdigit():
            rows.append({'unit':cells[1],'type':cells[2],'state':cells[3]})
        elif line.strip(): raise ValueError('unrecognized queued-job output')
    return rows


def holders(cfg):
    result=[]
    units=json.loads(control('list-units','--type=service','--state=active,activating,reloading,deactivating','--output=json'))
    infos=unit_infos([entry['unit'] for entry in units])
    for entry in units:
        unit=entry['unit']; info=infos.get(unit,{})
        project=identify(cfg,unit,info)
        if project is None: continue
        cpus=mask(info.get('AllowedCPUs','')) or group_cpus(info.get('ControlGroup',''))
        result.append({'project':project,'unit':unit,'cpus':sorted(cpus),
            'state':info.get('ActiveState'),'group':info.get('ControlGroup'),
            'invocation':info.get('InvocationID',''),'cpu_ns':info.get('CPUUsageNSec','')})
    # Foreground shell leases are live process identities, never just lock files.
    for path in cfg['runtime'].glob('exec-*.json'):
        try:
            row=json.loads(path.read_text())
            alive=process_start(row['pid'])==row['start']
            if not alive and row.get('process_group'):
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit(): continue
                    try:
                        if int(proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[2])==row['process_group']:
                            alive=True;break
                    except (OSError,ValueError,IndexError): continue
            if alive: result.append(row)
            else: path.unlink(missing_ok=True)
        except (OSError,ValueError,KeyError): continue
    tickets={}
    from cpu_guardian import scope_live
    for path in (cfg['runtime']/'tickets').glob('*.json'):
        try:
            row=json.loads(path.read_text())
            if row.get('status')=='admitted' and scope_live(row):
                if any(h.get('unit')==row['scope'] for h in result): continue
                info=unit_info(row['scope'])
                result.append({'project':row['project'],'unit':row['scope'],'cpus':row['cpus'],
                    'state':'live','pid':row['pid'],'invocation':info.get('InvocationID',''),
                    'cpu_ns':info.get('CPUUsageNSec','')})
            elif row.get('status')=='waiting': tickets[path.stem]=row
        except (OSError,ValueError,KeyError): continue
    if tickets:
        from cpu_guardian import waiting_pids
        for token,pid in waiting_pids(set(tickets)).items():
            row=tickets[token]
            result.append({'project':row['project'],'unit':'pending-foreground:'+str(pid),
                'cpus':row['cpus'],'state':'waiting','pid':pid})
    # Sleeping waiters and queued unit starts are capacity owners too.
    for entry in queued_jobs(control('list-jobs','--no-legend','--no-pager')):
        if entry.get('type')!='start': continue
        unit=entry['unit']
        if any(h.get('unit')==unit for h in result): continue
        info=unit_info(unit); project=identify(cfg,unit,info)
        if project is not None:
            reserved=reservations.status(cfg['file'])[project]['reserved']
            result.append({'project':project,'unit':unit,'cpus':reserved,'state':'queued'})
    return result


def no_conflicts(project, selected, live, exclude=None):
    for row in live:
        if row.get('unit')==exclude or row['project']==project: continue
        overlap=selected & set(row['cpus'])
        if overlap:
            raise ValueError('live/queued '+row.get('unit','foreground job')+' still owns CPUs '+str(sorted(overlap)))


def checked_conflicts(cfg,project,selected,exclude=None):
    # Every call rereads the authoritative table. Reuse only the expensive live
    # census for the SAME table/config bytes and already-checked CPUs (<=60s).
    # Flag, reservation and loan changes invalidate this cache immediately.
    generation=hashlib.sha256(cfg['file'].read_bytes()+cfg['config'].read_bytes()).hexdigest()
    path=cfg['runtime']/(project+'.admission.json')
    try: prior=json.loads(path.read_text())
    except (OSError,ValueError): prior={}
    if (prior.get('generation')==generation and time.time()-prior.get('time',0)<60
            and selected<=set(prior.get('cpus',[]))): return
    no_conflicts(project,selected,holders(cfg),exclude)
    atomic(path,{'generation':generation,'time':time.time(),'cpus':sorted(selected)})


def assert_drained(cfg, project, selected):
    for row in holders(cfg):
        if row['project']==project and (not row['cpus'] or selected & set(row['cpus'])):
            raise ValueError('not drained: '+row.get('unit','foreground job')+' is '+str(row.get('state','live')))


def set_mask(unit, selected):
    control('set-property','--runtime',unit,'AllowedCPUs='+','.join(map(str,sorted(selected))),'CPUAccounting=yes')


def admit(cfg, unit):
    info=unit_info(unit); project=identify(cfg,unit,info)
    if project is None: return None
    with locked(cfg):
        effective=mask(info.get('EffectiveCPUs','')) or mask(Path('/sys/devices/system/cpu/online').read_text())
        selected=allowed(cfg,project,effective,mask(info.get('AllowedCPUs','')))
        checked_conflicts(cfg,project,selected,exclude=unit)
        set_mask(unit,selected)
        return selected


def new_ticket(cfg,project,selected,cwd=None):
    token=secrets.token_hex(16)
    row={'project':project,'cpus':sorted(selected),'created':time.time(),'status':'waiting'}
    if cwd is not None: row['cwd']=str(cwd)
    atomic(cfg['runtime']/'tickets'/(token+'.json'),row)
    return token


def resolve_ticket(cfg,reference):
    if not re.fullmatch(r'[a-f0-9]{12}|[a-f0-9]{32}',reference):
        raise ValueError('invalid admission reference')
    matches=[p.stem for p in (cfg['runtime']/'tickets').glob(reference+'*.json')
        if re.fullmatch(r'[a-f0-9]{32}',p.stem)]
    if len(matches)!=1: raise ValueError('admission reference is missing or ambiguous; rerun the original command')
    return matches[0]


def quote_shell_command(command):
    single=shlex.quote(command)
    # Double quotes keep common single-quoted source/filters readable. Retain
    # literal expansion characters until the original shell executes the payload.
    if '!' in command: return single
    double='"'+command.replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`')+'"'
    return double if len(double)<=len(single) else single


def compact_shell(cfg,reference,command):
    ticket=resolve_ticket(cfg,reference)
    row=json.loads((cfg['runtime']/'tickets'/(ticket+'.json')).read_text())
    cwd=row.get('cwd')
    if not cwd or identify(cfg,info={'cwd':cwd})!=row['project']:
        raise ValueError('compact admission has no matching worktree')
    return exec_shell(cfg,row['project'],cwd,command,ticket)


def wait_ticket(cfg,project,token):
    if not re.fullmatch(r'[a-f0-9]{32}',token): raise ValueError('invalid admission ticket')
    path=cfg['runtime']/'tickets'/(token+'.json');deadline=time.monotonic()+15
    while True:
        row=json.loads(path.read_text())
        if row['project']!=project: raise ValueError('wrong project admission ticket')
        if row.get('status')=='denied': raise ValueError(row.get('reason','CPU admission denied'))
        if row.get('status')=='admitted':
            if row['start']!=process_start(os.getpid()): raise ValueError('admission PID identity mismatch')
            selected=allowed(cfg,project,set(os.sched_getaffinity(0)),set(row['cpus']))
            if set(os.sched_getaffinity(0))!=selected: raise ValueError('kernel scope affinity mismatch')
            return selected
        if time.monotonic()>=deadline: raise ValueError('CPU guardian did not admit this live process; inspect its service, do not bypass')
        time.sleep(.05)


def exec_shell(cfg, project, cwd, command, ticket=None):
    if ticket is None:
        selected=allowed(cfg,project,set(os.sched_getaffinity(0)),set())
        ticket=new_ticket(cfg,project,selected)
        os.execv(sys.executable,[sys.executable,str(Path(__file__).resolve()),'--config',str(cfg['config']),
            'exec','--project',project,'--cwd',str(cwd),'--ticket',ticket,'--command',command])
    selected=wait_ticket(cfg,project,ticket)
    child=subprocess.Popen(['/bin/bash','-lc',command],cwd=cwd,preexec_fn=os.setpgrp)
    try:
        # Preserve exact shell text, stdin, exit code, environment and parent caps.
        code=child.wait()
        try:
            atomic(cfg['runtime']/(project+'.last-exec.json'),{'time':time.time(),
                'cpus':sorted(selected),'pid':child.pid,'exit':code,'cwd':str(cwd)})
        except OSError as exc:
            if exc.errno not in {13,30}: raise
        return code
    except KeyboardInterrupt:
        try: os.killpg(child.pid,signal.SIGINT)
        except ProcessLookupError: pass
        return child.wait()


def standalone_control(command):
    try:
        lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|<>()');lexer.whitespace_split=True
        args=list(lexer)
    except ValueError: return False
    if any(set(a)<=set(';&|<>()') for a in args if a) or '\n' in command or '$(' in command or '`' in command:
        return False
    if len(args)>2 and Path(args[0]).name in {'python','python3'}:
        if Path(args[1]).resolve()==HERE/'cpu-reservations.py': return True
        if Path(args[1]).resolve()==Path(__file__).resolve() and args[2] in {'audit','review'}: return True
    return (len(args)>1 and Path(args[0]).name=='cpu-enforce'
        and args[1] in {'audit','review'})


def launch_shape(command,project,cfg):
    try: args=shlex.split(command)
    except ValueError: return
    if standalone_control(command) and '--project' in args:
        index=args.index('--project')
        if index+1>=len(args) or args[index+1]!=project:
            raise ValueError('this context may update only its own project row/review')
    if standalone_control(command):
        owner=next((a.split('=',1)[1] for a in args if a.startswith('--project=')),project)
        if owner!=project: raise ValueError('this context may update only its own project row/review')
    # Explicit launch escape routes are rejected before permissions/execution.
    # Embedded scripts still use the declared service-prefix contract and guard.
    for index,arg in enumerate(args):
        if Path(arg).name!='systemd-run': continue
        tail=args[index+1:]
        if '--help' in tail or '--version' in tail: continue
        if '--scope' in tail: raise ValueError('use the automatic foreground scope or an admitted project service')
        unit=next((a.split('=',1)[1] for a in tail if a.startswith('--unit=')),None)
        for option in ['--unit','-u']:
            if option in tail and tail.index(option)+1<len(tail): unit=tail[tail.index(option)+1]
        if not unit or not any(unit.startswith(p) for p in cfg['projects'][project]['unit_prefixes']):
            raise ValueError('systemd work needs an explicit registered project service prefix')


def compact_audit(result):
    lines=['project | active | usable | owned service CPU/s | live']
    for name,row in result['projects'].items():
        value=row['cpu_equivalents'];shown='?' if value is None else f'{value:.2f}'
        lines.append(f"{name} | {str(row['active']).lower()} | {row['available']} | {shown} | {row['live']}")
    lines.append('>=60s samples; exited work may be missing. CPU time is not accepted progress.')
    return '\n'.join(lines)


def prepare_control(cfg,project,command):
    """Resource bookkeeping only; never run arbitrary code outside the sandbox."""
    args=shlex.split(command)
    is_flags=len(args)>1 and Path(args[1]).resolve()==HERE/'cpu-reservations.py'
    rest=args[2:] if Path(args[0]).name in {'python','python3'} else args[1:]
    p=argparse.ArgumentParser(add_help=False)
    if is_flags:
        p.add_argument('--file',required=True,type=Path);p.add_argument('--project')
        p.add_argument('--cpus',type=reservations.cpus,default=set());p.add_argument('--drained',action='store_true')
        p.add_argument('--enforcement-config',type=Path)
        p.add_argument('action',choices=['status','active','inactive','borrow','release'])
        try: values=p.parse_args(rest)
        except SystemExit: raise ValueError('invalid reservation control arguments')
        if values.file.resolve()!=cfg['file']: raise ValueError('control table differs from declared authority')
        if values.action=='status': result=reservations.status(cfg['file'])
        else:
            if values.project!=project: raise ValueError('only your own project row may change')
            result=reservations.change(cfg['file'],project,values.action,values.cpus,values.drained,cfg['config'])
        return json.dumps(result,separators=(',',':'))
    p.add_argument('action',choices=['audit','review'])
    p.add_argument('--project');p.add_argument('--constraint');p.add_argument('--next')
    p.add_argument('--evidence',type=Path);p.add_argument('--json',action='store_true')
    try: values=p.parse_args(rest)
    except SystemExit: raise ValueError('invalid CPU review arguments')
    if values.action=='audit':
        result=sample(cfg)
        return json.dumps(result,separators=(',',':')) if values.json else compact_audit(result)
    if values.project!=project or not values.constraint or not values.next or not values.evidence:
        raise ValueError('review needs own project, constraint, next action and evidence')
    review(cfg,project,values.constraint,values.next,values.evidence)
    return 'CPU review recorded: '+project


def pre_hook(cfg, body, provider):
    if body.get('tool_name') not in {'Bash','exec_command'}: return {}
    original=body.get('tool_input',{})
    if not isinstance(original,dict): return {}
    command=original.get('command',original.get('cmd'))
    if not isinstance(command,str): return {}
    cwd=original.get('workdir') or body.get('cwd') or os.getcwd()
    project=identify(cfg,info={'cwd':cwd})
    if project is None: return {}
    try:
        launch_shape(command,project,cfg)
        if standalone_control(command):
            output=prepare_control(cfg,project,command)
            updated={**original,'command':shlex.join(['/usr/bin/python3','-c','print('+repr(output)+')'])}
            result={'hookEventName':'PreToolUse','updatedInput':updated}
            if provider=='codex': result['permissionDecision']='allow'
            return {'hookSpecificOutput':result}
        selected=allowed(cfg,project,set(os.sched_getaffinity(0)),set())
    except (OSError,ValueError) as exc:
        return {'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny',
            'permissionDecisionReason':'CPU reservation: '+str(exc)}}
    ticket=new_ticket(cfg,project,selected,cwd)
    runner=Path(cfg.get('compact_runner',str(Path.home()/'.local/bin/cpu-run')))
    if cfg.get('compact_commands') and cfg['config']==DEFAULT_CONFIG.resolve() and runner.is_file():
        resolved=shutil.which('cpu-run')
        label='cpu-run' if resolved and Path(resolved).resolve()==runner.resolve() else str(runner)
        wrapper=shlex.join([label,ticket[:12],'--'])+' '+quote_shell_command(command)
    else:
        wrapper=shlex.join(['/usr/bin/python3',str(Path(__file__).resolve()),'--config',str(cfg['config']),
            'exec','--project',project,'--cwd',str(cwd),'--ticket',ticket,'--command',command])
    updated={**original,'command':wrapper}
    if 'cmd' in original: updated['cmd']=wrapper
    result={'hookEventName':'PreToolUse','updatedInput':updated}
    # Codex requires allow for rewrites. Claude retains native approval decisions.
    if provider=='codex': result['permissionDecision']='allow'
    session=body.get('session_id') or body.get('thread_id')
    if session:
        identity=hashlib.sha256(str(session).encode()).hexdigest()[:24]
        atomic(cfg['runtime']/('hook-'+identity+'.json'),
            {'time':time.time(),'project':project,'provider':provider,'wrapped':True})
    return {'hookSpecificOutput':result}


def utilization(previous,current):
    elapsed=current['time']-previous['time']; result={}
    for key,row in current['usage'].items():
        entry=result.setdefault(row['project'],{'cpu_equivalents':0.0,'complete':True})
        old=previous['usage'].get(key)
        delta=row['cpu_ns']-(old['cpu_ns'] if old else 0)
        if elapsed>0: entry['cpu_equivalents']+=max(0,delta)/1e9/elapsed
    for key,row in previous['usage'].items():
        if key not in current['usage']:
            result.setdefault(row['project'],{'cpu_equivalents':0.0,'complete':True})['complete']=False
    return result


def sample(cfg):
    live=holders(cfg); now=time.time(); usage={}
    for row in live:
        value=row.get('cpu_ns','')
        if str(value).isdigit():
            usage[row.get('unit','')+':'+row.get('invocation','')]={'project':row['project'],'cpu_ns':int(value)}
    current={'time':now,'usage':usage}
    path=cfg['runtime']/'sample.json'
    try: previous=json.loads(path.read_text())
    except (OSError,ValueError): previous=current
    elapsed=now-previous['time']
    measured=utilization(previous,current) if elapsed>=60 else {}
    measured_at=now
    window_seconds=elapsed
    if elapsed<60:
        try:
            cached=json.loads((cfg['runtime']/'latest.json').read_text())
            measured={name:{'cpu_equivalents':row['cpu_equivalents'],'complete':row['complete']}
                for name,row in cached['projects'].items()}
            measured_at=cached.get('measured_at',cached['time'])
            window_seconds=cached.get('seconds',elapsed)
        except (OSError,ValueError,KeyError): pass
    if elapsed>=60 or not path.exists(): atomic(path,current)
    state=reservations.status(cfg['file'])
    result={'time':now,'measured_at':measured_at,'seconds':window_seconds,'projects':{},'holders':live,
        'limits':'Owned service/scope CPU-time only; exited/short-lived work may be missing. Not proof of useful accepted work.'}
    for project,row in state.items():
        result['projects'][project]={'active':row['active'],'available':len(row['usable']),
            'cpu_equivalents':measured.get(project,{}).get('cpu_equivalents'),
            'complete':measured.get(project,{}).get('complete',False),
            'live':sum(h['project']==project for h in live)}
    atomic(cfg['runtime']/'latest.json',result)
    return result


def review(cfg, project, constraint, next_action, evidence):
    if project not in cfg['projects'] or not next_action.strip() or not constraint.strip():
        raise ValueError('project, concrete constraint/action and next action required')
    evidence=Path(evidence).expanduser().resolve()
    if not evidence.is_file() or evidence.stat().st_size==0: raise ValueError('existing nonempty lane evidence file required')
    if evidence==cfg['file']: raise ValueError('review evidence belongs in the lane brief, never CPU.md')
    try: due=json.loads((cfg['runtime']/(project+'.feedback.json')).read_text())
    except (OSError,ValueError): due={}
    if due.get('pending') and evidence.stat().st_mtime<due['last']:
        raise ValueError('review evidence predates this checkpoint: update the current lane brief after inspecting live work')
    atomic(cfg['runtime']/(project+'.review.json'),{'time':time.time(),'constraint':constraint,
        'next':next_action,'evidence':str(evidence)})


def feedback_hook(cfg,body):
    if body.get('agent_id') or body.get('agent_transcript_path') or '/subagents/' in body.get('transcript_path',''):
        return {}
    project=identify(cfg,info={'cwd':body.get('cwd',os.getcwd())})
    if project is None: return {}
    root=cfg['runtime'];root.mkdir(parents=True,exist_ok=True)
    state=root/(project+'.feedback.json')
    with (root/(project+'.feedback.lock')).open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {}
        try: prior=json.loads(state.read_text())
        except (OSError,ValueError): prior={'last':time.time(),'pending':False}
        event=body.get('hook_event_name','PostToolUse')
        if event=='Stop':
            if not reservations.status(cfg['file'])[project]['active']: return {}
            if time.time()-prior['last']>=900:
                result=sample(cfg);row=result['projects'][project];now=time.time()
                prior={'last':now,'pending':True};atomic(state,prior)
            try: checked=json.loads((root/(project+'.review.json')).read_text())['time']>=prior['last']
            except (OSError,ValueError,KeyError): checked=False
            if prior.get('pending') and not checked:
                return {'decision':'block','reason':'CPU utilization review pending: refill admitted required work or record concrete constraint/next action using cpu-enforce review; no status-only acknowledgement.'}
            return {}
        now=time.time()
        if not state.exists():
            sample(cfg);atomic(state,prior);return {}
        if now-prior['last']<900: return {}
        result=sample(cfg);row=result['projects'][project]
        if not row['active']: return {}
        atomic(state,{'last':now,'pending':True})
        value=row['cpu_equivalents']; shown='?' if value is None else f'{value:.2f}'
        text=(f"CPU review due: owned service CPU={shown}/{row['available']} logical CPUs; incomplete accounting, sleeping waiters=0. "
            'Verify ready work/constraints and prior fix. Refill or record constraint+next action in lane brief; '
            'ack via cpu-enforce review --project '+project+' --constraint CODE --next ACTION --evidence FILE. No CPU.md log.')
        return {'hookSpecificOutput':{'hookEventName':event,'additionalContext':text}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT_CONFIG)
    commands=parser.add_subparsers(dest='action',required=True)
    p=commands.add_parser('admit');p.add_argument('--unit',required=True)
    p=commands.add_parser('exec');p.add_argument('--project',required=True);p.add_argument('--cwd',required=True);p.add_argument('--command',required=True);p.add_argument('--ticket')
    p=commands.add_parser('compact');p.add_argument('reference');p.add_argument('command')
    p=commands.add_parser('hook');p.add_argument('--provider',choices=['claude','codex'],required=True)
    p=commands.add_parser('audit');p.add_argument('--json',action='store_true')
    p=commands.add_parser('review');p.add_argument('--project',required=True);p.add_argument('--constraint',required=True);p.add_argument('--next',required=True);p.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args()
    body=None
    try:
        if args.action=='hook': body=json.load(sys.stdin)
        cfg=load_config(args.config)
        if args.action=='admit': admit(cfg,args.unit)
        elif args.action=='exec': return exec_shell(cfg,args.project,args.cwd,args.command,args.ticket)
        elif args.action=='compact': return compact_shell(cfg,args.reference,args.command)
        elif args.action=='audit':
            result=sample(cfg)
            if args.json: print(json.dumps(result,separators=(',',':')))
            else: print(compact_audit(result))
        elif args.action=='review': review(cfg,args.project,args.constraint,args.next,args.evidence)
        elif args.action=='hook':
            if body.get('hook_event_name')=='PreToolUse':
                result=pre_hook(cfg,body,args.provider)
            else: result=feedback_hook(cfg,body)
            print(json.dumps(result))
    except (OSError,ValueError,subprocess.SubprocessError,KeyError) as exc:
        if args.action=='hook' and isinstance(body,dict):
            # A broken CPU configuration must not capture unrelated projects.
            # The installer retains only the last registered roots for this check.
            try:
                roots=json.loads(args.config.with_name('roots.json').read_text())
                cwd=body.get('tool_input',{}).get('workdir') or body.get('cwd',os.getcwd())
                if not any(in_root(cwd,root) for root in roots):
                    print('{}');return 0
            except (OSError,ValueError,TypeError): pass
        print('CPU enforcement: '+str(exc),file=sys.stderr)
        return 255 if args.action=='admit' else 2
    return 0


if __name__=='__main__': sys.exit(main())
