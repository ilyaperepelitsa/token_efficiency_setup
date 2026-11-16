#!/usr/bin/env python3
"""Validate the deliberately narrow public observation export; no raw records."""
import json
from pathlib import Path


def exact_keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('unexpected evidence schema fields')


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('evidence counters must be nonnegative integers')


def validate(data):
    exact_keys(data, ['schema_version','window_minutes','workloads_matched',
                     'accepted_work_comparison_available','usage','lead_contexts'])
    if data['schema_version'] != 1 or data['window_minutes'] != 15:
        raise ValueError('unsupported observation format')
    for key in ['workloads_matched','accepted_work_comparison_available']:
        if type(data[key]) is not bool:
            raise ValueError('measurement limits require explicit booleans')
    exact_keys(data['usage'], ['before','after'])
    metrics=['responses','new_input_and_writes','cached_input','output']
    for phase in ['before','after']:
        exact_keys(data['usage'][phase], metrics)
        for value in data['usage'][phase].values():
            counter(value)
    if not isinstance(data['lead_contexts'],list) or len(data['lead_contexts']) != 2:
        raise ValueError('expected two anonymous context observations')
    labels=[]
    for sample in data['lead_contexts']:
        exact_keys(sample, ['sample','before_input','after_input'])
        labels.append(sample['sample'])
        counter(sample['before_input']);counter(sample['after_input'])
    if labels != ['A','B']:
        raise ValueError('only anonymous A/B labels are allowed')
    return {key:round((data['usage']['after'][key]/data['usage']['before'][key]-1)*100,1)
            if data['usage']['before'][key] else None for key in metrics}


def main():
    path=Path(__file__).resolve().parents[1]/'data/anonymized-observations.json'
    changes=validate(json.loads(path.read_text()))
    print('Allowlisted evidence schema passed; usage change (%): '+json.dumps(changes))


if __name__=='__main__':
    main()
