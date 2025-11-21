# time-logging model
In time logs, each entry is a tuple (id, start, duration, tags, description).
The idea is that each time log entry corresponds to logging time spent doing some broad/specific activity.
Queries like 
```SELECT count(*), sum(duration) IN time_logs WHERE tags LIKE '%sometag%'``` 
should be possible.
Workers should prompt the user to input how they've spent their time lastly.

## Why time logging
It should help users identify which activities are taking most of their time and if that distribution match with the perceived return of each activity.
