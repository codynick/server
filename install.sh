#!/usr/bin/env bash
set -Eeuo pipefail
exec 8>/run/lock/codynick-server-install.lock
flock -n 8 || { echo 'An installation is already running.'; exit 1; }
SOURCE=$1
VERSION=0.1.0
export DEBIAN_FRONTEND=noninteractive
OLD=$(readlink -f /opt/codynick-server/current 2>/dev/null || true)
ACTIVATED=0
failure(){
  echo "INSTALLATION FAILED at line $1."
  if [[ $ACTIVATED == 1 && -n $OLD && -d $OLD ]]; then
    ln -sfn "$OLD" /opt/codynick-server/current
    systemctl restart codynick-server-runner codynick-server-web || true
    echo 'Previous application restored. Keep the installation log.'
  fi
}
trap 'failure $LINENO' ERR
echo "Installing CodyNick Server $VERSION"
apt-get -o DPkg::Lock::Timeout=600 -o Acquire::Retries=5 update
apt-get -o DPkg::Lock::Timeout=600 -o Acquire::Retries=5 install -y python3-venv nginx docker.io ca-certificates curl
systemctl enable --now docker
id codynick-web >/dev/null 2>&1 || useradd --system --home-dir /var/lib/codynick-server --shell /usr/sbin/nologin codynick-web
install -d -m 750 -o codynick-web -g codynick-web /var/lib/codynick-server
install -d -m 700 /var/backups/codynick-server
if [[ -f /var/lib/codynick-server/classroom.sqlite ]]; then
  python3 - <<'PY'
import sqlite3,datetime
name='/var/backups/codynick-server/pre-install-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite'
with sqlite3.connect('/var/lib/codynick-server/classroom.sqlite') as src,sqlite3.connect(name) as dst:src.backup(dst)
PY
fi
RELEASE="/opt/codynick-server/releases/$VERSION"
install -d /opt/codynick-server/releases
if [[ -d $RELEASE ]]; then
  # A repair gets a new directory; the live release is never changed in place.
  RELEASE="$RELEASE-$(date +%s)"
fi
install -d "$RELEASE"
cp -a "$SOURCE/server" "$SOURCE/static" "$SOURCE/templates" "$SOURCE/runtime" "$SOURCE/requirements.txt" "$RELEASE/"
python3 -m venv "$RELEASE/venv"
"$RELEASE/venv/bin/pip" install --disable-pip-version-check --retries 5 -r "$RELEASE/requirements.txt"
docker build --pull -t codynick-classroom:0.1.0 "$RELEASE/runtime"
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 128m --pids-limit 32 codynick-classroom:0.1.0 python -c 'import CodyNick,Dashboard,SpriteStage;print("Runtime imports OK")'
if [[ ! -f /etc/codynick-server.env ]]; then
  SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
  printf 'CN_SECRET=%s\nCN_DATA=/var/lib/codynick-server\nCN_MAX_JOBS=2\n' "$SECRET" >/etc/codynick-server.env
  chmod 640 /etc/codynick-server.env
  chown root:codynick-web /etc/codynick-server.env
fi
install -m 644 "$SOURCE/deploy/codynick-server-web.service" /etc/systemd/system/
install -m 644 "$SOURCE/deploy/codynick-server-runner.service" /etc/systemd/system/
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  if [[ ! -f /var/backups/codynick-server/nginx-default ]]; then cp -L /etc/nginx/sites-enabled/default /var/backups/codynick-server/nginx-default; fi
  rm /etc/nginx/sites-enabled/default
fi
install -m 644 "$SOURCE/deploy/nginx.conf" /etc/nginx/sites-available/codynick-server
ln -sfn /etc/nginx/sites-available/codynick-server /etc/nginx/sites-enabled/codynick-server
nginx -t
ln -sfn "$RELEASE" /opt/codynick-server/current
ACTIVATED=1
systemctl daemon-reload
systemctl enable --now codynick-server-runner codynick-server-web nginx
systemctl restart codynick-server-runner codynick-server-web
systemctl reload nginx
ACCOUNT_INFO=$(runuser -u codynick-web -- "$RELEASE/venv/bin/python" "$RELEASE/server/admin.py")
if [[ $ACCOUNT_INFO == *'Initial password:'* ]]; then
  printf '%s\n' "$ACCOUNT_INFO" >/var/backups/codynick-server/initial-login.txt
  chmod 600 /var/backups/codynick-server/initial-login.txt
fi
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1/health | grep -q '0.1.0'; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1/health | grep -q '0.1.0'
systemctl is-active --quiet codynick-server-runner codynick-server-web
runuser -u codynick-web -- /usr/bin/python3 "$RELEASE/server/smoke.py"
if [[ -f /var/backups/codynick-server/initial-login.txt ]]; then
  cat /var/backups/codynick-server/initial-login.txt
else
  echo "$ACCOUNT_INFO"
fi
echo "CodyNick Server $VERSION: READY"
echo 'Open the VM web address. With NAT port forwarding: http://127.0.0.1:8080'
echo 'This is a LAN-only prototype. Do not expose HTTP port 80 to the public internet.'
