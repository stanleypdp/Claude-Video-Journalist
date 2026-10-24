---
tags: [video-read, number-check]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In the stored run of the clip I replaced one number in the cached transcript on purpose (55.2 became 55.7) to test the safety net. The cache is in `./data` and the result in `OUTPUT/clip`. Rebuild the result from the cache with the video-read skill (set DATA_DIR to the absolute path of ./data; no new model calls) and tell me whether the pipeline flagged the planted error, and where.

Input files: data/, OUTPUT/
