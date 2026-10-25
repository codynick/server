# CodyNick Classroom Server

## 0.1.0: Local classroom prototype

Separate from the Raspberry Pi edition. Ubuntu Server 26.04 x86-64 only.
No AI, USB bridge, hotspot management, or RPi driver installation.

**One fixed installation / repair / upgrade command:**

```bash
wget -4 -O /tmp/codynick-server-setup.sh "https://raw.githubusercontent.com/codynick/server/main/setup.sh?$(date +%s)" && sudo bash /tmp/codynick-server-setup.sh
```

Keep the VM running. An SSH disconnect does not terminate the background install.
Follow progress after reconnecting:

```bash
sudo tail -f /var/log/codynick-server-install.log
```

Success: `CodyNick Server 0.1.0: READY`. The log prints the unique initial teacher
password. It is also stored root-only in `/var/backups/codynick-server/initial-login.txt`.
Repairs preserve existing teacher accounts and do not reset passwords.

VirtualBox NAT forwarding: host IP `127.0.0.1`, host port `8080`, guest port `80`.
Open http://127.0.0.1:8080 on Windows. SSH remains host port 2222 -> guest port 22.
This prototype uses HTTP for local testing only; HTTPS/domain provisioning and
external scheduled backups must be added before public VPS deployment.

## Test sequence

1. Sign in as teacher. In Students create `student1` and `student2`, with unique
   non-empty passwords. No shared default student passwords exist.
2. Open separate browser profiles or browsers and sign in as each student.
3. Open Examples / Temperature and Dashboard, then Run. Change the temperature
   slider in Gadgets and inspect Dashboard. Each student's values must be independent.
4. Run LED Colors. Only that student's simulated LEDs should change.
5. In Block Coding drag blocks from Control/Gadgets/Text, then Run and Stop.
6. Save a named project. The other student must not see it. Load must not run it.
   Download/upload block designs as `.codynick`; Delete requires confirmation.
7. Run an infinite Python loop. Stop must end it without affecting the other user.
8. Close all tabs for one account: the program stops within approximately 125 seconds.
9. Restart the web application: saved projects and accounts must remain.

## Prototype scope and limits

This is a deliberately small first baseline, not feature parity with the RPi tools.
The simulator has fixed CJP LEDs, temperature, joystick input, seven-segment output,
and matrix-text output. No drag/drop gadget toolbox, matrix pixel animation or buzzer
yet. The single sprite supports `Stage.go_to(x,y)` and `Stage.say(text)`.
Blockly currently has basic control, operators, text, variables, LED, temperature,
seven-segment and sprite-speech blocks. The full RPi block catalog comes later.
Dashboard supports numeric cards and a simple history graph. It is session output,
not persisted historical telemetry. No teacher project access or assignments.

The simulation API is a small server-specific facade, NOT a full copy of CodyNick.py.
Physical `CN()` fails explicitly; use `Simulator()`. Only supplied demo syntax is
supported in this baseline. Scripts have Python's standard library, without AI.

There is no application-wide concurrent-program cap. One program runs per account;
actual capacity depends on available server resources. Each has 128 MB RAM, 0.5 CPU,
32 processes, no network, read-only system files, no host mounts, a 32 MB ephemeral
workspace and 8 MB temporary directory. Runtime files disappear when it stops.
Save source through the web UI. Each account may save 100 projects of up to 64 KB.
Output is capped at 128 KB per account. Programs stop after 30 minutes maximum or
120 seconds without an authenticated status poll. Multiple tabs share one runtime
per account; closing one tab does not stop a program if another remains open.
Any old `CN_MAX_JOBS` setting is ignored. Short passwords are accepted for creation
and reset (non-empty, at most 128 characters). Strong passwords remain recommended.

Containers isolate accidental classroom misuse but are not a hardened public
arbitrary-code service. Do not allow public registration or untrusted users.
The web service is unprivileged and has no Docker socket access. A separate local
broker fixes all Docker security options and receives requests via a restricted
Unix socket. No student package installation or outbound script internet access.

## Operations and upgrade behavior

Data: `/var/lib/codynick-server/classroom.sqlite` (accounts and projects).
Application: `/opt/codynick-server/releases/`; `current` selects the active release.
Configuration: `/etc/codynick-server.env`. Keep its signing secret private.
Services: `codynick-server-web`, `codynick-server-runner`, `nginx`, `docker`.
The installer takes a consistent SQLite backup before upgrades and never deletes
student projects. Backup files on this VM are not off-device disaster recovery.
Upgrades stop running programs and retain saved work. The first schema is additive.
If activation fails, the installer restores the previous application symlink when
available. Broader release selection/downgrade tooling is not implemented yet.
Automatic public VPS installation is intentionally not offered in this prototype.

## Release integrity

`setup.sh` pins an immutable release tag and SHA256 of `release.json`. Every source
file downloaded is checked against that manifest before installing. Never move a
published tag. To issue a new version update constants, run `tools/seal.py`, test,
then publish a new tag and main together. Large external dependencies require
internet during install (Ubuntu packages, Python packages and Docker base image).
The initial Python base tag is not digest-pinned; reproducible runtime image pinning
is required before a production server release.
