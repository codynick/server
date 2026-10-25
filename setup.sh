#!/usr/bin/env bash
set -Eeuo pipefail
VERSION=0.2.0
REF=v0.2.0-rpi-classroom
MANIFEST_SHA=73c5de1207682b8fc1cac8fc7bcd1fd20de6d40ff324ed8238bbf90d18f97de4
BASE="https://raw.githubusercontent.com/codynick/server/$REF"
if [[ $EUID -ne 0 ]]; then echo 'Run this installer with sudo.'; exit 1; fi
if [[ $(uname -m) != x86_64 ]]; then echo 'This server edition requires x86-64 Ubuntu.'; exit 1; fi
source /etc/os-release
VERSION=0.2.0
if [[ $ID != ubuntu || $VERSION_ID != 26.04 ]]; then echo 'This prototype requires Ubuntu Server 26.04 x86-64.'; exit 1; fi
command -v curl >/dev/null || { apt-get update; apt-get install -y curl ca-certificates; }
install -d -m 700 /var/lib/codynick-bootstrap
exec 9>/run/lock/codynick-server-entry.lock
flock -n 9 || { echo 'Another setup command is preparing the release.'; exit 1; }
if systemctl is-active --quiet codynick-server-install; then
  echo 'Installation is already running. Showing progress; Ctrl+C only closes this display.'
  exec tail -n 40 -f /var/log/codynick-server-install.log
fi
STAGE=$(mktemp -d /var/lib/codynick-bootstrap/release.XXXXXX)
trap 'rm -rf -- "$STAGE"' ERR
curl -4fSL --retry 5 --connect-timeout 15 --max-time 180 "$BASE/release.json" -o "$STAGE/release.json"
echo "$MANIFEST_SHA  $STAGE/release.json" | sha256sum -c -
curl -4fSL --retry 5 --connect-timeout 15 --max-time 300 "https://codeload.github.com/codynick/server/tar.gz/refs/tags/$REF" -o "$STAGE/source.tar.gz"
python3 - "$STAGE" <<'PY'
import hashlib,json,pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1])
manifest=json.loads((root/'release.json').read_text())
with tarfile.open(root/'source.tar.gz') as archive:
    for member in archive:
        parts=pathlib.PurePosixPath(member.name).parts[1:]
        name='/'.join(parts)
        if name not in manifest['files']: continue
        if not member.isfile() or '..' in parts: raise SystemExit('Invalid release entry')
        raw=archive.extractfile(member).read()
        if hashlib.sha256(raw).hexdigest()!=manifest['files'][name]: raise SystemExit('Checksum failed: '+name)
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
for name,digest in manifest['files'].items():
    if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest: raise SystemExit('Incomplete release: '+name)
PY
touch /var/log/codynick-server-install.log
chmod 600 /var/log/codynick-server-install.log
FIRST_LINE=$(( $(wc -l </var/log/codynick-server-install.log) + 1 ))
systemctl reset-failed codynick-server-install.service 2>/dev/null || true
systemd-run --unit=codynick-server-install --collect --property=Type=exec \
  --property=StandardOutput=append:/var/log/codynick-server-install.log \
  --property=StandardError=append:/var/log/codynick-server-install.log \
  /bin/bash "$STAGE/install.sh" "$STAGE"
echo "CodyNick Server $VERSION installation started in the background."
echo 'Follow progress: sudo tail -f /var/log/codynick-server-install.log'
echo "Success ends with: CodyNick Server $VERSION: READY"
trap - ERR
flock -u 9
echo 'Progress follows. Ctrl+C closes this display only; background installation continues.'
tail -n +"$FIRST_LINE" -f /var/log/codynick-server-install.log &
FOLLOWER=$!
trap 'kill "$FOLLOWER" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
while systemctl is-active --quiet codynick-server-install.service; do sleep 1; done
sleep 1
