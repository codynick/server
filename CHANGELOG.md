# Changes

## 0.2.0 - 2026-10-24

Remove the ten-character student password minimum, including password resets.
Remove the shared two-program execution cap; old CN_MAX_JOBS configuration is ignored.
Keep per-program CPU, memory, process and runtime safeguards.
Replace the reduced prototype tools with the actual RPi 0.11.0 main panel, IDE,
Blockly, simulator, sprite stage, dashboard, docs and guides. Add teacher-only
Student Management on the original main panel. Isolate the original paths/services
inside private user containers; keep each user's dashboard in a separate database.
Preserve accounts and migrate original prototype projects without deleting exports.
Same-origin simulator navigation and live installer progress. AI and USB remain deferred.

## 0.1.0 - 2026-10-24

First LAN-only classroom prototype. Teacher-created student accounts and resets,
private named projects, isolated Python Run/Stop, bounded output, simple Blockly,
simulated gadgets, dashboard cards and a sprite. Single-command background installer
with persistent logs, checksum verification and preserved SQLite data. AI/USB and
public HTTPS deployment are deferred. See README for exact supported subset.
