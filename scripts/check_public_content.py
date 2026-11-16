#!/usr/bin/env python3
"""Check tracked/unignored publication candidates without printing matching values."""
from pathlib import Path
import re
import subprocess
import sys

PATTERNS = {
    'personal absolute path':re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+(?:/|\b)'),
    'Windows user path':re.compile(r'[A-Za-z]:\\Users\\[^\\\s]+'),
    'API key shape':re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),
    'GitHub token shape':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'AWS access key shape':re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
    'private key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'credential URL':re.compile(r'https?://[^\s/@:]+:[^\s/@]+@'),
}


def inspect(path, text):
    issues=[]
    if path.suffix in {'.jsonl','.sqlite','.pem','.key'} or path.name in {'.env','.keys'}:
        issues.append('runtime/credential file')
    for label,pattern in PATTERNS.items():
        if pattern.search(text):
            issues.append(label)
    return issues


def main():
    root=Path(__file__).resolve().parents[1]
    out=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root)
    failed=[]
    for raw in set(out.decode().split('\0'))- {''}:
        p=root/raw
        if p.is_symlink():
            failed.append((raw,'publication symlink requires manual review'));continue
        if not p.is_file():
            continue
        try:
            text=p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            failed.append((raw,'unexpected binary'));continue
        failed += [(raw,issue) for issue in inspect(p,text)]
    for path,issue in sorted(failed):
        print(f'{path}: {issue}')
    if failed:
        return 1
    print('Public-content checks passed (pattern checks complement manual review).')
    return 0


if __name__=='__main__':
    sys.exit(main())
