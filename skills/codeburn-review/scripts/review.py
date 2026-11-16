#!/usr/bin/env python3
"""Bounded 15-minute usage comparisons and passive, main-session reminders."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

METRICS = ('responses', 'new_input', 'cache_write', 'cached', 'output')
INTERVAL = 900
STAMP = re.compile(rb'"timestamp"\s*:\s*"([^"]+)"')


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return result.astimezone(timezone.utc)


def compare(provider, transcript, end):
    transcript = Path(transcript)
    start = end - timedelta(minutes=30)
    split = end - timedelta(minutes=15)
    paths = [transcript]
    if provider == 'claude':
        paths += sorted((transcript.with_suffix('') / 'subagents').glob('*.jsonl'))
    messages = {}
    errors = skipped_large = notices = 0
    legacy = False
    for path in paths:
        who = 'main' if path == transcript else path.stem
        modern = False
        prior_info = None
        try:
            stream = path.open('rb')
        except OSError:
            errors += 1
            continue
        with stream:
            while True:
                line = stream.readline(1024 * 1024)
                if not line:
                    break
                if not line.endswith(b'\n') and len(line) == 1024 * 1024:
                    skipped_large += 1
                    while line and not line.endswith(b'\n'):
                        line = stream.readline(1024 * 1024)
                    continue
                match = STAMP.search(line[:400])
                if match:
                    try:
                        at = utc(match[1].decode())
                    except ValueError:
                        errors += 1
                        continue
                    if not start <= at < end:
                        continue
                try:
                    row = json.loads(line)
                    if provider == 'claude' and row.get('type') != 'assistant':
                        continue
                    if provider == 'codex' and not (
                        row.get('type') == 'token_usage_record' or
                        (row.get('type') == 'event_msg' and
                         row.get('payload', {}).get('type') == 'token_count')):
                        continue
                    at = utc(row['timestamp'])
                    if not start <= at < end:
                        continue
                    if provider == 'claude':
                        if row.get('type') != 'assistant':
                            continue
                        msg = row['message']
                        if msg.get('model') == '<synthetic>':
                            notices += 1
                            continue
                        ident = msg.get('id') or row.get('uuid')
                        u = msg.get('usage')
                        if not isinstance(u, dict):
                            errors += 1
                            continue
                        values = {'new_input': u.get('input_tokens', 0),
                            'cache_write': u.get('cache_creation_input_tokens', 0),
                            'cached': u.get('cache_read_input_tokens', 0),
                            'output': u.get('output_tokens', 0)}
                    else:
                        p = row.get('payload', {})
                        if row.get('type') == 'token_usage_record':
                            modern = True
                            ident = p.get('response_id') or (str(path), row.get('ordinal'))
                            u = p['usage']
                        elif row.get('type') == 'event_msg' and p.get('type') == 'token_count' and not modern:
                            info = p.get('info')
                            if not info or not info.get('last_token_usage'):
                                continue
                            identity = json.dumps(info, sort_keys=True)
                            if identity == prior_info:
                                continue
                            prior_info = identity
                            ident = (str(path), identity)
                            u = info['last_token_usage']
                            legacy = True
                        else:
                            continue
                        cached = u.get('cached_input_tokens', 0)
                        write = u.get('cache_write_input_tokens', 0)
                        values = {'new_input': max(0, u.get('input_tokens', 0)-cached-write),
                            'cache_write': write, 'cached': cached,
                            'output': u.get('output_tokens', 0)}
                    if not ident or any(not isinstance(v, int) or v < 0 for v in values.values()):
                        errors += 1
                        continue
                    old = messages.get(ident)
                    if old is None:
                        messages[ident] = {'at': at, 'who': who, **values}
                    else:
                        for key, value in values.items():
                            old[key] = max(old[key], value)
                except (ValueError, KeyError, TypeError, AttributeError):
                    errors += 1

    def aggregate(rows):
        return {'responses': len(rows), **{k:sum(r[k] for r in rows) for k in METRICS[1:]}}
    current_rows = [r for r in messages.values() if split <= r['at'] < end]
    previous_rows = [r for r in messages.values() if start <= r['at'] < split]
    current, previous = aggregate(current_rows), aggregate(previous_rows)
    hottest = []
    for who in {r['who'] for r in current_rows}:
        rows = sorted((r for r in current_rows if r['who'] == who), key=lambda r:r['at'])
        latest = rows[-1]
        hottest.append({'agent':who, 'responses':len(rows),
            'context':sum(latest[k] for k in ['new_input','cache_write','cached']),
            'cache_write':sum(r['cache_write'] for r in rows),
            'output':sum(r['output'] for r in rows)})
    hottest.sort(key=lambda r:r['context'], reverse=True)
    return {'schema':1, 'source':'local transcript adapter (CodeBurn has date-only CLI ranges)',
        'provider':provider, 'window_minutes':15, 'current_from':split.isoformat(),
        'until':end.isoformat(), 'previous_from':start.isoformat(),
        'current':current, 'previous':previous,
        'delta_pct':{k:round((current[k]/previous[k]-1)*100,1) if previous[k] else None for k in METRICS},
        'largest_contexts':hottest[:3], 'active_contexts':len(hottest),
        'accepted_batches':None, 'cpu_utilization':None,
        'data_complete':not (errors or skipped_large),
        'unreadable_records':errors, 'oversize_lines_skipped':skipped_large,
        'synthetic_notices':notices, 'legacy_codex_records':legacy,
        'scope':'session + workers' if provider=='claude' else 'this Codex rollout only; child rollouts not included',
        'limits':'Recorded tokens, not subscription quota or dollars. Output includes reasoning; do not add it twice. '
                 'Accepted work and CPU data must come from existing project receipts. null deltas mean no baseline.'}


def compact(result, exact_path):
    def short(value):
        if value is None:
            return '?'
        for divisor, suffix in [(1e9,'B'),(1e6,'M'),(1e3,'k')]:
            if abs(value)>=divisor:
                return f'{value/divisor:.3g}{suffix}'
        return str(value)
    def clock(value):
        try:
            return utc(value).strftime('%H:%M')
        except (ValueError,TypeError,AttributeError):
            return '?'
    lines=[f"usage15m UTC now={clock(result.get('current_from'))}-{clock(result.get('until'))} "
           f"prev={clock(result.get('previous_from'))}-{clock(result.get('current_from'))} "
           f"{result.get('provider','?')}", 'metric | prev | now | delta']
    for key,label in [('new_input','new'),('cache_write','write'),('cached','cached'),
                      ('output','output'),('responses','calls')]:
        a=result.get('previous',{}).get(key)
        b=result.get('current',{}).get(key)
        d=result.get('delta_pct',{}).get(key)
        delta=f'{d:+.3g}%' if isinstance(d,(int,float)) else '?'
        lines.append(f'{label} | {short(a)} | {short(b)} | {delta}')
    contexts=[]
    for row in result.get('largest_contexts',[])[:3]:
        name=str(row.get('agent','?'))
        if len(name)>24:
            name=name[:18]+'~'+hashlib.sha256(name.encode()).hexdigest()[:4]
        contexts.append(name+':'+short(row.get('context')))
    lines.append('ctx '+(' '.join(contexts) or 'none'))
    lines.append(f"complete={int(bool(result.get('data_complete')))} "
                 f"legacy={int(bool(result.get('legacy_codex_records')))} "
                 f"accepted={short(result.get('accepted_batches'))} cpu={short(result.get('cpu_utilization'))}; "
                 +('scope=main+workers' if result.get('provider')=='claude' else 'scope=rollout-only'))
    if result.get('error'):
        lines.append('error='+str(result['error'])[:40])
    lines.append('Recorded tokens, not quota/cost; ?=unmeasured. Exact: '+str(exact_path))
    text='\n'.join(lines)
    # Only metadata is rendered; if an unusual path fills the budget, retain the
    # actionable metrics and move the oversized reference into a short notice.
    if len(text)>840:
        text='\n'.join(lines[:-1])+ '\nExact JSON saved in ~/.cache/codeburn-review/.'
    return text[:840]


def reminder(body, state_root, now, report):
    if body.get('agent_id') or body.get('agent_transcript_path'):
        return None
    transcript = body.get('transcript_path', '')
    if '/subagents/' in transcript:
        return None
    session = body.get('session_id') or body.get('thread_id')
    if not session:
        return None
    state_root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(session).encode()).hexdigest()[:24]
    with (state_root / (key+'.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        state = state_root / (key+'.json')
        try:
            data = json.loads(state.read_text())
        except (OSError, ValueError):
            data = {'last_reminder':now}
            state.write_text(json.dumps(data))
            return None
        if now-data.get('last_reminder',now) < INTERVAL:
            return None
        # Claim before computing so errors and overlapping tools cannot flood reminders.
        data['last_reminder'] = now
        state.write_text(json.dumps(data))
        try:
            result = report()
        except Exception as exc:
            result = {'data_complete':False, 'error':type(exc).__name__,
                      'next':'Use codeburn-review report with the actual session/rollout path; do not repair indexes.'}
        exact = state_root / (key+'.latest.json')
        exact.write_text(json.dumps(result))
        context = ('codeburn-review due: verify prior fix; <=3 lines result/action/evidence. '
            'Preserve jobs/gates. No rescan unless a concrete anomaly.\n'+compact(result,exact))
        assert len(context)<=1000
        return {'hookSpecificOutput':{'hookEventName':body.get('hook_event_name','PostToolUse'),
                                     'additionalContext':context}}


def resolve(provider, session, transcript):
    if transcript:
        path=Path(transcript).expanduser().resolve()
    elif provider=='claude':
        import uuid
        uuid.UUID(session)
        found=list((Path.home()/'.claude/projects').glob('*/'+session+'.jsonl'))
        if len(found)!=1:
            raise ValueError('session transcript not uniquely found')
        path=found[0]
    else:
        raise ValueError('Codex needs --transcript with the actual rollout path')
    if not path.is_file():
        raise ValueError('transcript does not exist')
    if provider=='codex':
        with path.open() as stream:
            meta=json.loads(stream.readline()).get('payload', {})
        if isinstance(meta.get('source'),dict) and 'subagent' in meta['source']:
            raise ValueError('worker rollout: main-session reviews only')
    return path


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['report','hook'])
    p.add_argument('--provider',choices=['claude','codex'],default='claude')
    p.add_argument('--session')
    p.add_argument('--transcript')
    p.add_argument('--until',type=utc)
    p.add_argument('--json',action='store_true',help='Full exact JSON; default is a compact table')
    args=p.parse_args()
    end=args.until or datetime.now(timezone.utc)
    if args.mode=='report':
        result=compare(args.provider,resolve(args.provider,args.session,args.transcript),end)
        if not args.json:
            key=hashlib.sha256(str(args.session or args.transcript).encode()).hexdigest()[:24]
            root=Path.home()/'.cache/codeburn-review';root.mkdir(parents=True,exist_ok=True)
            exact=root/(key+'.latest.json');exact.write_text(json.dumps(result))
            print(compact(result,exact))
            return
    else:
        if (Path.home()/'.config/codeburn-review/disabled').exists():
            return
        try:
            body=json.loads(sys.stdin.read(2*1024*1024))
            result=reminder(body,Path.home()/'.cache/codeburn-review',time.time(),
                lambda:compare(args.provider,resolve(args.provider,
                    body.get('session_id'),body.get('transcript_path')),end))
        except Exception:
            return  # Advisory hook never interrupts product work.
    if result is not None:
        print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    main()
