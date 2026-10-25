#!/usr/bin/env bash
set -Eeuo pipefail
VERSION=0.1.0
REF=v0.1.0-classroom-prototype
MANIFEST_SHA=0ce7b53a947f4f1b2c07398e94f31b4898df523ecfc18dcb260e64d885bf050f
BASE="https://raw.githubusercontent.com/codynick/server/$REF"
if [[ $EUID -ne 0 ]]; then echo 'Run this installer with sudo.'; exit 1; fi
if [[ $(uname -m) != x86_64 ]]; then echo 'This server edition requires x86-64 Ubuntu.'; exit 1; fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 26.04 ]]; then echo 'This prototype requires Ubuntu Server 26.04 x86-64.'; exit 1; fi
command -v curl >/dev/null || { apt-get update; apt-get install -y curl ca-certificates; }
install -d -m 700 /var/lib/codynick-bootstrap
exec 9>/run/lock/codynick-server-entry.lock
flock -n 9 || { echo 'Another setup command is preparing the release.'; exit 1; }
if systemctl is-active --quiet codynick-server-install; then
  echo 'Installation is already running. Follow: sudo tail -f /var/log/codynick-server-install.log'; exit 0
fi
STAGE=$(mktemp -d /var/lib/codynick-bootstrap/release.XXXXXX)
trap 'rm -rf -- "$STAGE"' ERR
curl -4fSL --retry 5 --connect-timeout 15 --max-time 180 "$BASE/release.json" -o "$STAGE/release.json"
echo "$MANIFEST_SHA  $STAGE/release.json" | sha256sum -c -
python3 - "$STAGE" "$BASE" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);base=sys.argv[2]
manifest=json.loads((root/'release.json').read_text())
for name,digest in manifest['files'].items():
    rel=pathlib.PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts: raise SystemExit('Invalid release path')
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['curl','-4fSL','--retry','5','--connect-timeout','15','--max-time','180',base+'/'+name,'-o',str(target)],check=True)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=digest: raise SystemExit('Checksum failed: '+name)
PY
touch /var/log/codynick-server-install.log
chmod 600 /var/log/codynick-server-install.log
systemctl reset-failed codynick-server-install.service 2>/dev/null || true
systemd-run --unit=codynick-server-install --collect --property=Type=exec \
  --property=StandardOutput=append:/var/log/codynick-server-install.log \
  --property=StandardError=append:/var/log/codynick-server-install.log \
  /bin/bash "$STAGE/install.sh" "$STAGE"
echo "CodyNick Server $VERSION installation started in the background."
echo 'Follow progress: sudo tail -f /var/log/codynick-server-install.log'
echo "Success ends with: CodyNick Server $VERSION: READY"
