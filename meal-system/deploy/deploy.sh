#!/usr/bin/env bash
# Deploy the meal planner to the slate host.
#
#   ./deploy/deploy.sh                    # ship code + (re)start the service on :8200
#   ./deploy/deploy.sh planyourmeals      # ...and wire up https://planyourmeals.duckdns.org
#
# Production is planyourmeals.duckdns.org. The no-arg form is the normal deploy — DNS and
# the Caddy site block are already in place, so the label is only needed to (re)wire them.
#
# The DuckDNS subdomain must already exist in your duckdns.org account — the
# token only updates the IP of domains you already own. Everything else is
# idempotent and safe to re-run.
#
# Slate is never touched: the Caddyfile is backed up and validated before reload,
# and the meal planner gets its own site block, service, port, and data dir.
set -euo pipefail

HOST=ubuntu@140.245.216.42
KEY=~/.ssh/slate_server
SRC="$(cd "$(dirname "$0")/.." && pwd)"
SUB="${1:-}"                      # duckdns label, e.g. "planyourmeals" (no .duckdns.org)
REMOTE=/home/ubuntu/meal-system
DATA=/home/ubuntu/meal-system-data

ssh_() { ssh -i "$KEY" -o ConnectTimeout=15 "$HOST" "$@"; }

echo "==> shipping code to $REMOTE"
rsync -az --delete \
  --exclude 'data/' --exclude '.git' --exclude '__pycache__' \
  --exclude 'meal-plan.md' --exclude 'pantry-week1.md' --exclude 'nutrient-cadence.md' \
  -e "ssh -i $KEY" "$SRC/" "$HOST:$REMOTE/"

echo "==> service + db"
ssh_ "set -e
  mkdir -p $DATA
  sudo cp $REMOTE/deploy/meals.service /etc/systemd/system/meals.service
  sudo systemctl daemon-reload
  MEALS_DB=$DATA/meals.db python3 $REMOTE/app.py import-csv
  sudo systemctl enable --now meals
  sudo systemctl restart meals
  sleep 1
  curl -fsS http://127.0.0.1:8200/api/health && echo ' <- api healthy'
"

if [ -z "$SUB" ]; then
  echo "==> done (no subdomain given). Service is live on 127.0.0.1:8200."
  echo "    Create the subdomain at duckdns.org, then re-run: ./deploy/deploy.sh <label>"
  exit 0
fi

echo "==> DNS: pointing $SUB.duckdns.org at this host"
ssh_ "set -e
  # reuse the existing token; add \$SUB to the 5-minutely refresh if it isn't there
  TOKEN=\$(grep -oE 'token=[^&\"]*' ~/duckdns/duck.sh | head -1 | cut -d= -f2)
  DOMS=\$(grep -oE 'domains=[^&\"]*' ~/duckdns/duck.sh | head -1 | cut -d= -f2)
  case \",\$DOMS,\" in
    *\",$SUB,\"*) : ;;
    *) sed -i \"s/domains=\$DOMS/domains=\$DOMS,$SUB/\" ~/duckdns/duck.sh ;;
  esac
  OUT=\$(curl -s \"https://www.duckdns.org/update?domains=$SUB&token=\$TOKEN&ip=140.245.216.42\")
  echo \"  duckdns: \$OUT\"
  [ \"\$OUT\" = OK ] || { echo '  !! duckdns said KO — is $SUB created in your duckdns.org account?'; exit 1; }
"

echo "==> Caddy: site block + basic auth (reusing slate's AUTH_USER/AUTH_PASS)"
ssh_ "set -e
  CF=/etc/caddy/Caddyfile
  sudo cp \$CF \$CF.bak.\$(date +%s)

  if grep -q '^$SUB.duckdns.org' \$CF; then
    echo '  site block already present — leaving it alone'
  else
    # pull creds from slate's env without ever echoing them
    AU=\$(grep -E '^AUTH_USER=' /home/ubuntu/slate-engine/.env | cut -d= -f2- | tr -d '\"')
    AP=\$(grep -E '^AUTH_PASS=' /home/ubuntu/slate-engine/.env | cut -d= -f2- | tr -d '\"')
    HASH=\$(caddy hash-password --plaintext \"\$AP\")
    sudo tee -a \$CF >/dev/null <<EOF

$SUB.duckdns.org {
    basic_auth {
        \$AU \$HASH
    }
    @api path /api/*
    handle @api {
        reverse_proxy 127.0.0.1:8200
    }
    handle {
        root * $REMOTE
        file_server
    }
    encode gzip
}
EOF
    echo '  appended site block'
  fi

  # never reload a broken config in front of slate
  sudo caddy validate --config \$CF --adapter caddyfile >/dev/null && echo '  caddyfile valid'
  sudo systemctl reload caddy && echo '  caddy reloaded'
"

echo "==> verifying"
sleep 3
code=$(curl -s -o /dev/null -w '%{http_code}' "https://$SUB.duckdns.org/api/health" || true)
echo "  https://$SUB.duckdns.org/api/health -> $code (401 = auth is on, as expected)"
slate=$(curl -s -o /dev/null -w '%{http_code}' https://myslate.duckdns.org/health || true)
echo "  slate still healthy -> $slate"
echo "==> done: https://$SUB.duckdns.org"
