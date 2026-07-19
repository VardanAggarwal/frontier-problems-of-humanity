#!/usr/bin/env bash
# Deploy the meal planner to the slate host — git-based.
#
#   ./deploy/deploy.sh                    # ship the committed HEAD + restart the service on :8200
#   ./deploy/deploy.sh planyourmeals      # ...and wire up https://planyourmeals.duckdns.org
#
# Production is planyourmeals.duckdns.org. The no-arg form is the normal deploy — DNS and
# the Caddy site block are already in place, so the label is only needed to (re)wire them.
#
# WHAT SHIPS: the commit on origin/main, not your working tree. The server holds a sparse
# clone of the repo (meal-system/ only) and hard-resets to origin/main. So what's deployed is
# always a SHA you can `git show`, and an uncommitted experiment can never reach production by
# accident. The flip side: commit and push before deploying — the guards below stop you if you
# haven't, rather than quietly shipping something stale.
#
# The repo is PUBLIC, so the server clones over HTTPS read-only and needs no credentials. If it
# is ever made private, the server needs a read-only deploy key and REPO_URL must become the
# git@ form.
#
# Untracked files (data/, meal-plan.md, pantry-week1.md, nutrient-cadence.md) simply never ship —
# git carries only what's committed, so the old rsync --exclude list is now implicit.
#
# The database lives outside the checkout ($DATA) and is never touched by the reset.
#
# Slate is never touched: the Caddyfile is backed up and validated before reload,
# and the meal planner gets its own site block, service, port, and data dir.
set -euo pipefail

HOST=ubuntu@140.245.216.42
KEY=~/.ssh/slate_server
SRC="$(cd "$(dirname "$0")/.." && pwd)"
SUB="${1:-}"                      # duckdns label, e.g. "planyourmeals" (no .duckdns.org)
REPO_URL=https://github.com/VardanAggarwal/frontier-problems-of-humanity.git
CLONE=/home/ubuntu/fph            # sparse clone of the whole repo…
REMOTE=$CLONE/meal-system         # …of which only this subtree is checked out and served
DATA=/home/ubuntu/meal-system-data
BRANCH=main

ssh_() { ssh -i "$KEY" -o ConnectTimeout=15 "$HOST" "$@"; }

cd "$SRC"

echo "==> checking the tree is deployable"
# 1. nothing uncommitted under meal-system/ — the deploy ships commits, so a dirty file here
#    would silently not go out. Changes elsewhere in the repo are none of this deploy's business.
if ! git diff --quiet -- . || ! git diff --cached --quiet -- . ; then
  echo "  !! uncommitted changes under meal-system/ — commit them first:"
  git status --short -- . | sed 's/^/     /'
  exit 1
fi

# 2. HEAD must already be on the remote branch, or the server would reset to something older
#    than what you're looking at. This reports; it does not push for you — pushing is a
#    decision, and a deploy script is the wrong place to make it silently.
git fetch -q origin "$BRANCH"
if ! git merge-base --is-ancestor HEAD "origin/$BRANCH"; then
  echo "  !! HEAD ($(git rev-parse --short HEAD)) is not on origin/$BRANCH — push first:"
  echo "     git push origin $BRANCH"
  exit 1
fi
echo "  HEAD $(git rev-parse --short HEAD) is on origin/$BRANCH ✓"

echo "==> pulling $BRANCH on the host"
ssh_ "set -e
  if [ ! -d $CLONE/.git ]; then
    git clone --filter=blob:none --no-checkout $REPO_URL $CLONE
    cd $CLONE && git sparse-checkout set meal-system && git checkout $BRANCH
  fi
  cd $CLONE
  git fetch --quiet origin $BRANCH
  git reset --hard --quiet origin/$BRANCH
  echo \"  now at \$(git log --oneline -1)\"
"

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
