---
tags: [video-read, language]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

The clips in `OUTPUT/clips` are English videos. Rebuild every card from the cache in `./data` with the video-read skill (set DATA_DIR to the absolute path of ./data; no model calls) and tell me which clips came through and which did not, and why.

Input files: data/, OUTPUT/
