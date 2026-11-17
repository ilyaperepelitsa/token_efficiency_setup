#!/usr/bin/env python3
"""Move verified waiting processes into CPU-only scopes; never execute their code.

The process keeps its original mount/network/seccomp sandbox. Requests are created
by trusted native hooks; the sandbox can only read its acknowledgement.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time

import cpu_enforcement as guard


def waiting_pids(tokens):
    found={}
    if not tokens: return found
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            args=(path/'cmdline').read_bytes().split(b'\0')
            # Do not inspect the embedded source/command argument.
            if b'--command' in args: args=args[:args.index(b'--command')]
            script=str(Path(guard.__file__).resolve()).encode()
            if script not in args: continue
            index=args.index(script)+1
            if args[index]==b'--config':index+=2
            elif args[index].startswith(b'--config='):index+=1
            if args[index]==b'compact':
                reference=args[index+1].decode()
                if not re.fullmatch(r'[a-f0-9]{12}|[a-f0-9]{32}',reference): continue
                matches=[t for t in tokens if t.startswith(reference)]
                if len(matches)!=1: continue
                token=matches[0]
            elif args[index]==b'exec' and b'--ticket' in args:
                token=args[args.index(b'--ticket')+1].decode()
            else: continue
            if token in tokens: found[token]=int(path.name)
        except (OSError,ValueError,IndexError): continue
    return found


def scope_properties(pid,selected):
    text=Path('/proc',str(pid),'cgroup').read_text().strip()
    current=Path('/sys/fs/cgroup'+text.split('::',1)[1])
    scope_slice=next((p for p in [current,*current.parents] if p.name.endswith('.slice')),None)
    if scope_slice is None: raise ValueError('no supported user slice')
    properties=[('PIDs','au',[pid]),('AllowedCPUs','ay',bitmap(selected)),
                ('Slice','s',scope_slice.name),('CPUAccounting','b',True),
                ('CollectMode','s','inactive-or-failed')]
    limit=None
    for directory in [current,*current.parents]:
        if directory==scope_slice: break
        for name in ['memory.max','memory.high','memory.swap.max','cpu.max']:
            try: value=(directory/name).read_text().strip()
            except OSError: continue
            if value.split()[0]!='max':
                raise ValueError('bounded parent job: retain its existing CPU boundary and resource profile')
        try:
            value=(directory/'pids.max').read_text().strip()
            if value!='max': limit=min(limit or int(value),int(value))
        except OSError: pass
    if limit is not None: properties.append(('TasksMax','t',limit))
    return properties


def bitmap(selected):
    result=[0]*(max(selected)//8+1)
    for cpu in selected: result[cpu//8]|=1<<(cpu%8)
    return result


def start_scope(name,properties):
    args=['busctl','--user','call','org.freedesktop.systemd1','/org/freedesktop/systemd1',
          'org.freedesktop.systemd1.Manager','StartTransientUnit','ssa(sv)a(sa(sv))',
          name,'fail',str(len(properties))]
    for key,kind,value in properties:
        args += [key,kind]
        if kind.startswith('a'): args += [str(len(value)),*map(str,value)]
        elif kind=='b': args += ['true' if value else 'false']
        else: args += [str(value)]
    args+=['0']
    subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)


def admit_ticket(cfg,path,row,pid):
    with guard.locked(cfg):
        start=guard.process_start(pid)
        if start is None: return
        selected=guard.allowed(cfg,row['project'],set(os.sched_getaffinity(pid)),set(row['cpus']))
        guard.checked_conflicts(cfg,row['project'],selected)
        current_group=Path('/proc',str(pid),'cgroup').read_text().strip().split('::',1)[1]
        current=Path('/sys/fs/cgroup'+current_group)
        existing=set()
        for directory in [current,*current.parents]:
            try: existing=guard.mask((directory/'cpuset.cpus.effective').read_text());break
            except OSError: continue
        if existing and existing<=selected and current.name.endswith(('.service','.scope')):
            guard.atomic(path,{**row,'status':'admitted','pid':pid,'start':start,
                'scope':current.name,'group':current_group,'admitted':time.time()})
            return
        name='cpu-exec-'+path.stem+'.scope'
        properties=scope_properties(pid,selected)
        start_scope(name,properties)
        deadline=time.monotonic()+5
        while True:
            info=guard.unit_info(name);actual=guard.mask(info.get('EffectiveCPUs',''))
            group=Path('/proc',str(pid),'cgroup').read_text()
            if actual and actual<=selected and name in group: break
            if time.monotonic()>=deadline: raise ValueError('scope CPU boundary not established for waiting process')
            time.sleep(.05)
        guard.atomic(path,{**row,'status':'admitted','pid':pid,'start':start,
            'scope':name,'group':info.get('ControlGroup',''),'admitted':time.time()})


def scope_live(row):
    if guard.process_start(row['pid'])==row['start']: return True
    group=row.get('group','')
    if not group: return False
    try:
        events=dict(line.split() for line in Path('/sys/fs/cgroup'+group,'cgroup.events').read_text().splitlines())
        return events.get('populated')=='1'
    except FileNotFoundError: return False
    except OSError: return True


def serve(cfg):
    directory=cfg['runtime']/'tickets';directory.mkdir(parents=True,exist_ok=True)
    last_sample=0
    while True:
        cfg=guard.load_config(cfg['config'])
        pending={}
        for path in directory.glob('*.json'):
            try:
                row=json.loads(path.read_text())
                if row.get('status')=='admitted':
                    if not scope_live(row): path.unlink(missing_ok=True)
                elif row.get('status')=='waiting': pending[path.stem]=(path,row)
                elif time.time()-row.get('created',0)>60: path.unlink(missing_ok=True)
            except (OSError,ValueError,KeyError): continue
        matches=waiting_pids(set(pending))
        for token,(path,row) in pending.items():
            try:
                if token in matches: admit_ticket(cfg,path,row,matches[token])
                elif time.time()-row['created']>300: path.unlink(missing_ok=True)
            except (OSError,ValueError,subprocess.SubprocessError) as exc:
                guard.atomic(path,{**row,'status':'denied','reason':str(exc)[:240]})
        if time.monotonic()-last_sample>=60:
            try: guard.sample(cfg)
            except (OSError,ValueError,subprocess.SubprocessError): pass
            last_sample=time.monotonic()
        youngest=min((time.time()-row['created'] for _,row in pending.values()),default=99)
        time.sleep(.1 if youngest<2 else .5 if not pending else 1)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=guard.DEFAULT_CONFIG)
    serve(guard.load_config(parser.parse_args().config))
