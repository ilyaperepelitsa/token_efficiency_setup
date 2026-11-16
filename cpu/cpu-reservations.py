#!/usr/bin/env python3
"""Atomic CPU flags/loans; configured projects require verified drained jobs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile


def cpus(value):
    if value.strip() in {'','-'}:return set()
    result={int(x.strip()) for x in value.split(',')}
    if any(x<0 for x in result):raise ValueError('negative CPU')
    return result


def read(path):
    text=path.read_text();rows={}
    limits={}
    for line in text.splitlines():
        for label in ['Logical CPUs','System reserve','Project CPU limit']:
            if line.startswith(label+':'):
                if label in limits:raise ValueError('duplicate global limit')
                limits[label]=line.split(':',1)[1].strip()
    if set(limits)!={'Logical CPUs','System reserve','Project CPU limit'}:
        raise ValueError('global logical count, system reserve and project limit required')
    total=int(limits['Logical CPUs']);system=cpus(limits['System reserve'])
    maximum=int(limits['Project CPU limit'])
    if total<=0 or maximum<0 or maximum>total-len(system) or any(c>=total for c in system):
        raise ValueError('invalid global CPU limit')
    for line in text.splitlines():
        if not line.startswith('|'):continue
        cells=[x.strip() for x in line.strip('|').split('|')]
        if cells[0] in {'Project','---'}:continue
        if len(cells)!=5 or cells[3] not in {'true','false'}:
            raise ValueError('invalid reservation row')
        name=cells[0]
        if name in rows:raise ValueError('duplicate project')
        reserved=cpus(cells[2])
        if int(cells[1])!=len(reserved) or any(c>=total for c in reserved):
            raise ValueError('reservation count/range mismatch')
        rows[name]={'reserved':reserved,'active':cells[3]=='true',
                    'borrowed':cpus(cells[4]),'line':line}
    if sum(len(r['reserved']) for r in rows.values())>maximum:
        raise ValueError('project reservations exceed global limit')
    owners={c:'host' for c in system};claimed=set()
    for name,row in rows.items():
        for cpu in row['reserved']:
            if cpu in owners:raise ValueError('overlapping reservations')
            owners[cpu]=name
    for name,row in rows.items():
        if row['borrowed'] and not row['active']:raise ValueError('inactive borrower')
        for cpu in row['borrowed']:
            if cpu not in owners or owners[cpu] in {name,'host'} or cpu in claimed:
                raise ValueError('invalid or duplicate loan')
            claimed.add(cpu)
    return text,rows,owners


def status(path):
    _,rows,owners=read(Path(path));lent=set().union(*(r['borrowed'] for r in rows.values()))
    return {name:{'active':r['active'],'reserved':sorted(r['reserved']),
        'borrowed':sorted(r['borrowed']),
        'usable':sorted((r['reserved']-lent)|{c for c in r['borrowed']
            if not rows[owners[c]]['active']}) if r['active'] else [],
        'return_at_boundary':sorted(c for c in r['borrowed'] if rows[owners[c]]['active'])}
        for name,r in rows.items()}


def change(path, project, action, selected, drained, enforcement_config=None):
    path=Path(path)
    with path.with_name(path.name+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        text,rows,owners=read(path)
        if project not in rows or project=='host':raise ValueError('unknown/non-project owner')
        mine=rows[project]
        if action=='active':mine['active']=True
        elif action=='inactive':
            if not drained:raise ValueError('verify jobs, waiters and future queued launches drained; pass --drained')
            if mine['borrowed']:raise ValueError('release borrowed CPUs before going inactive')
            verify_drained(path,project,mine['reserved'],enforcement_config)
            mine['active']=False
        elif action=='borrow':
            if not mine['active'] or not selected:raise ValueError('active borrower and explicit CPUs required')
            claimed=set().union(*(r['borrowed'] for r in rows.values()))
            for cpu in selected:
                owner=owners.get(cpu)
                if owner is None or owner in {project,'host'} or rows[owner]['active'] or cpu in claimed:
                    raise ValueError('CPU not available from an inactive unclaimed project pool')
            for owner in {owners[cpu] for cpu in selected}:
                verify_drained(path,owner,{cpu for cpu in selected if owners[cpu]==owner},enforcement_config)
            mine['borrowed']|=selected
        elif action=='release':
            if not drained:raise ValueError('verify borrowed-core jobs drained; pass --drained')
            if not selected or not selected<=mine['borrowed']:raise ValueError('not your recorded loan')
            verify_drained(path,project,selected,enforcement_config)
            mine['borrowed']-=selected
        else:raise ValueError('unknown action')
        def listing(values):return ','.join(str(x) for x in sorted(values)) or '-'
        row=f"| {project} | {len(mine['reserved'])} | {listing(mine['reserved'])} | {str(mine['active']).lower()} | {listing(mine['borrowed'])} |"
        updated=text.replace(mine['line'],row,1)
        if updated!=text:
            with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
                f.write(updated);temp=Path(f.name)
            temp.chmod(path.stat().st_mode & 0o777);os.replace(temp,path)
    return status(path)


def verify_drained(path,project,selected,enforcement_config=None):
    # Import only for real configured reservations. Isolated/uninstalled tables
    # retain the cooperative protocol, with --drained as an explicit assertion.
    config=Path(enforcement_config) if enforcement_config else Path.home()/'.config/cpu-reservations/config.json'
    if not config.is_file():
        if enforcement_config:raise ValueError('missing enforcement configuration')
        return
    raw=json.loads(config.read_text())
    if Path(raw['file']).expanduser().resolve()!=path.resolve():
        if enforcement_config:raise ValueError('enforcement table mismatch')
        return
    import importlib.util
    spec=importlib.util.spec_from_file_location('cpu_enforcement',Path(__file__).with_name('cpu_enforcement.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cfg=module.load_config(config)
    if project not in cfg['projects']:raise ValueError('project missing enforcement registration')
    module.assert_drained(cfg,project,selected)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--file',required=True,type=Path)
    p.add_argument('--project')
    p.add_argument('--cpus',type=cpus,default=set())
    p.add_argument('--drained',action='store_true',help='Owner assertion: checked no live/queued work still uses the released capacity')
    p.add_argument('--enforcement-config',type=Path,help='Explicit configuration for an isolated reservation table')
    p.add_argument('action',choices=['status','active','inactive','borrow','release'])
    a=p.parse_args()
    try:
        result=status(a.file) if a.action=='status' else change(a.file,a.project,a.action,a.cpus,a.drained,a.enforcement_config)
    except (OSError,ValueError) as e:p.exit(1,str(e)+'\n')
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':main()
