---
urgency: ride-along
component: backend-scripts
audience: operators
---
The offline posture_stats.py and dump_face_readings.py scripts now process at most 290 s (4:50) of any video by default, to cap memory use. Pass `--max-seconds N` to change it, or `--max-seconds 0` for a deliberate full-length run on another machine.
