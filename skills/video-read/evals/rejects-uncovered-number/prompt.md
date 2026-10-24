---
tags: [video-read, validator]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

I have a finished video-read result for one clip in `OUTPUT/clip`. Use the video-read skill's coverage check on it and tell me whether I can trust the card. If something fails, tell me which number and why. Don't change any files.

Input files: OUTPUT/
