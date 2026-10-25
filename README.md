# CodyNick Classroom Server

## 0.2.0: Original RPi tools with private classroom workspaces

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

Setup now follows live progress automatically; Ctrl+C only closes that display.
Success: `CodyNick Server 0.2.0: READY`. The log prints the unique initial teacher
password. It is also stored root-only in `/var/backups/codynick-server/initial-login.txt`.
Repairs preserve existing teacher accounts and do not reset passwords.

VirtualBox NAT forwarding: host IP `127.0.0.1`, host port `8080`, guest port `80`.
Open http://127.0.0.1:8080 on Windows. SSH remains host port 2222 -> guest port 22.
This prototype uses HTTP for local testing only; HTTPS/domain provisioning and
external scheduled backups must be added before public VPS deployment.

## Test sequence

1. Sign in as teacher. On the original main panel, open Student Management and create `student1` and `student2`, with unique
   non-empty passwords. No shared default student passwords exist.
2. Open separate browser profiles or browsers and sign in as each student.
3. Open Gadget Simulator from the main panel. Add temperature and seven-segment
   gadgets from the original drag/drop toolbox, then open the IDE in another tab.
   Run `CodyNick examples/dashboard/temperature_on_dashboard.py`. Change the simulator
   temperature and inspect Dashboard. Each student's values must be independent.
4. Run `CodyNick examples/simulator/simulator_demo.py`. Only that student's LEDs
   and browser buzzer audio should change (enable sound in the simulator).
5. In Block Coding use the original General/Sprites/Hardware categories and Run/Stop.
6. Save a named project. The other student must not see it. Load must not run it.
   Download/upload block designs as `.codynick`; Delete requires confirmation.
7. Run an infinite Python loop. Stop must end it without affecting the other user.
8. Close all tabs for one account: the program stops within approximately 125 seconds.
9. Restart the web application: saved projects and accounts must remain.

## Original interfaces and behavior

The actual RPi 0.11.0 main panel, PHP IDE, Blockly, sprite stage, drag/drop simulator,
dashboard, docs, teacher guides and gadget tests are bundled under `upstream/`.
The substituted 0.1.0 tool interfaces are no longer served. A build-time adapter
changes only connection paths, workspace storage and server identity, and adds the
teacher-only Student Management card. Existing Run/Stop and file operations remain
the original PHP implementation. Every user gets their own `/home/client`, PHP
session, simulator and sprite services, active script and MariaDB dashboard database.
The browser stays on one authenticated origin, including the simulator; no hardcoded
IP address, exposed simulator token or separate port is needed.

The full original CodyNick gadget-command implementations and Dashboard/SpriteStage
Python libraries are retained. For this simulation-only phase `CN()` connects to the
private simulator, just as `Simulator()` does. This explicit server adaptation is not
physical USB support. AI methods and examples remain in the documentation/source as
references but their runtimes/models are NOT installed. No teacher assignments or
access to student work is introduced. Teacher guides require the teacher role.

Old prototype Python projects are copied to `Migrated projects` on first workspace
creation. Old Blockly exports are preserved there as `.codynick` files; unsupported
prototype block IDs are not automatically translated. The original SQLite projects
also remain untouched. New RPi-style named designs are saved separately per user.

## Runtime safeguards

There is no application-wide concurrent-program cap. One program runs per account;
actual capacity depends on available server resources. Each private tool container
has 256 MB RAM, 0.5 CPU, 64 processes, no network, read-only application files, a
64 MB workspace and 16 MB temporary directory. Its only host mount is the MariaDB
Unix socket, authenticated using a unique account restricted to its own database.
No Docker socket or host student directories are mounted into the container.
Source/design saves and scene changes trigger validated atomic workspace snapshots;
dashboard data is stored persistently in the user's database. Idle containers are
snapshotted and removed after ten minutes. They are restored on the next tool request.
Runtime-created files are snapshotted on idle/shutdown; save important work before
an upgrade. Disk or host crashes can lose changes since the last completed snapshot.
Programs stop after 30 minutes maximum or 120 seconds without an authenticated page
heartbeat. Multiple tabs share one runtime per account. Closing one tab does not stop
it if another authenticated tool page remains open. IDE output is bounded at 256 KB.
Any old `CN_MAX_JOBS` setting is ignored. Short passwords are accepted for creation
and reset (non-empty, at most 128 characters). Strong passwords remain recommended.

Containers isolate accidental classroom misuse but are not a hardened public
arbitrary-code service. Do not allow public registration or untrusted users.
The web service is unprivileged and has no Docker socket access. A separate local
broker fixes all Docker security options and receives requests via a restricted
Unix socket. No student package installation or outbound script internet access.

## Operations and upgrade behavior

Data: `/var/lib/codynick-server/classroom.sqlite` (accounts and original prototype projects),
`/var/lib/codynick-workspaces/` (root-only credentials and validated private snapshots),
and MariaDB `cn_<user ID>` databases (dashboard cards).
Application: `/opt/codynick-server/releases/`; `current` selects the active release.
Configuration: `/etc/codynick-server.env`. Keep its signing secret private.
Services: `codynick-server-web`, `codynick-server-runner`, `nginx`, `docker`, `mariadb`.
The installer takes a consistent SQLite backup before upgrades and never deletes
student projects. Backup files on this VM are not off-device disaster recovery.
Upgrades stop running programs and retain saved work. The first schema is additive.
If activation fails, the installer restores the previous application symlink when
available. Broader release selection/downgrade tooling is not implemented yet.
Automatic public VPS installation is intentionally not offered in this prototype.

## Release integrity

`setup.sh` pins an immutable release tag and SHA256 of `release.json`. Every source
file in the source archive is checked against that manifest before installing. Never move a
published tag. To issue a new version update constants, run `tools/seal.py`, test,
then publish a new tag and main together. Large external dependencies require
internet during install (Ubuntu packages, Python packages and Docker base image).
The initial Python base tag is not digest-pinned; reproducible runtime image pinning
is required before a production server release.
