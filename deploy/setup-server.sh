#!/usr/bin/env bash
# Set up or update Replisto on an Ubuntu/Debian server. Run as root, with the site's domain:
#
#   bash setup-server.sh example.com
#
# The site and panel are served on the domain itself and the API on api.<domain>; both need a
# DNS A record pointing at this server for HTTPS to work.
#
# First run: installs Docker and git, downloads the code to /opt/replisto, writes .env with
# fresh secrets, opens ports 80 and 443 and starts everything. Later runs: download the latest
# code and restart; .env is kept as it is.
#
# A private repository asks for a GitHub token (read-only access to the repository's contents
# is enough); it is kept in /root/.git-credentials for the next updates.
set -euo pipefail

DOMAIN="${1:-}"
REPO="${REPO:-https://github.com/notaliranjbar/Replisto.git}"
BRANCH="${BRANCH:-master}"
DIR="${DIR:-/opt/replisto}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mWARNING: %s\033[0m\n' "$*"; }
die() { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

install_tools() {
  say "Installing git, curl and Docker"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git openssl >/dev/null
  if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
  fi
  docker compose version >/dev/null 2>&1 || die "Docker Compose is missing (docker compose version failed)"
  systemctl enable --now docker >/dev/null 2>&1 || true
}

fetch_code() {
  if [ -d "$DIR/.git" ]; then
    say "Downloading the latest code into $DIR"
    git -C "$DIR" pull --ff-only origin "$BRANCH"
    return
  fi
  say "Downloading the code into $DIR"
  if git clone --quiet --branch "$BRANCH" "$REPO" "$DIR" 2>/dev/null; then
    return
  fi
  echo "The repository is private (or unreachable)."
  local token
  read -rsp "GitHub token with read access to the repository: " token </dev/tty
  echo
  [ -n "$token" ] || die "no token given"
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$token" >/root/.git-credentials
  chmod 600 /root/.git-credentials
  git clone --quiet --branch "$BRANCH" "$REPO" "$DIR" || die "could not download $REPO"
}

# Replace KEY=... in .env (values may contain / & and spaces, so no sed).
set_env() {
  local key="$1" value="$2"
  awk -v k="$key" -v v="$value" 'BEGIN { done = 0 }
    $0 ~ "^" k "=" { print k "=" v; done = 1; next } { print }
    END { if (!done) print k "=" v }' .env >.env.tmp
  mv .env.tmp .env
}

write_env() {
  cd "$DIR"
  if [ -f .env ]; then
    say "Keeping the existing .env"
    return
  fi
  say "Writing .env with fresh secrets"
  cp .env.example .env
  set_env ENVIRONMENT production
  set_env PANEL_DOMAIN "$DOMAIN"
  set_env API_DOMAIN "api.$DOMAIN"
  set_env FRONTEND_URL "https://$DOMAIN"
  set_env PUBLIC_BASE_URL "https://api.$DOMAIN"
  set_env CORS_ORIGINS "[\"https://$DOMAIN\"]"
  set_env SUPPORT_EMAIL "support@$DOMAIN"
  set_env SMTP_FROM "Replisto <no-reply@$DOMAIN>"
  set_env POSTGRES_PASSWORD "$(openssl rand -hex 24)"
  set_env SECRET_KEY "$(openssl rand -hex 32)"
  # A Fernet key: 32 random bytes in URL-safe base64.
  set_env ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
  set_env META_WEBHOOK_VERIFY_TOKEN "$(openssl rand -hex 16)"
  # Shops can't connect Instagram until the Meta app's ID and secret are in .env.
  set_env INSTAGRAM_ENABLED false
  # Secrets: readable by root only.
  chmod 600 .env
}

open_firewall() {
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    say "Opening ports 80 and 443 in the firewall"
    ufw allow OpenSSH >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
  fi
}

check_dns() {
  local ip host found ok=1
  ip="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
  say "Checking DNS (this server: ${ip:-unknown})"
  for host in "$(grep '^PANEL_DOMAIN=' "$DIR/.env" | cut -d= -f2)" \
    "$(grep '^API_DOMAIN=' "$DIR/.env" | cut -d= -f2)"; do
    found="$(getent ahostsv4 "$host" | awk 'NR == 1 { print $1 }')"
    if [ -z "$found" ]; then
      warn "$host has no A record yet. Add one pointing to ${ip:-this server}."
      ok=0
    elif [ -n "$ip" ] && [ "$found" != "$ip" ]; then
      warn "$host points to $found, not to this server (${ip})."
      ok=0
    else
      echo "$host -> $found"
    fi
  done
  [ "$ok" = 1 ] || warn "HTTPS starts working a few minutes after the DNS records point here."
}

start() {
  cd "$DIR"
  say "Building and starting (the first build takes a few minutes)"
  docker compose up -d --build --remove-orphans
  say "Waiting for the API"
  for _ in $(seq 1 60); do
    if docker compose exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')" \
      >/dev/null 2>&1; then
      docker compose ps
      local panel api
      panel="$(grep '^PANEL_DOMAIN=' .env | cut -d= -f2)"
      api="$(grep '^API_DOMAIN=' .env | cut -d= -f2)"
      say "Replisto is running: https://$panel (API: https://$api)"
      echo "Keep a copy of $DIR/.env somewhere safe: without ENCRYPTION_KEY the stored"
      echo "Instagram connections can't be read. Logs: cd $DIR && docker compose logs -f api"
      return
    fi
    sleep 5
  done
  docker compose ps
  docker compose logs --tail 50 api
  die "the API did not start; see the log above"
}

main() {
  [ "$(id -u)" = 0 ] || die "run as root"
  [ -n "$DOMAIN" ] || [ -f "$DIR/.env" ] || die "usage: bash setup-server.sh <domain>"
  install_tools
  fetch_code
  write_env
  open_firewall
  check_dns
  start
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
