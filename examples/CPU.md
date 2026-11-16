# CPU reservations — synthetic example; replace for your host

Logical CPUs: 8
System reserve: 0,1
Project CPU limit: 6

| Project | Count | Reserved | Active | Borrowed |
| --- | --- | --- | --- | --- |
| alpha | 4 | 2,3,4,5 | true | - |
| beta | 2 | 6,7 | false | - |

Current state only. Replace rows in place when the allocation changes.
No transactions, changelog, timestamps, job status or utilization diary.
There is no line/project-count limit; global capacity and disjoint reservations bind.
