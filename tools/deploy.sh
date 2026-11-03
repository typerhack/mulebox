#!/usr/bin/env bash
# Build mulebox from this checkout and install it on a build machine over ssh.
#
#   tools/deploy.sh <ssh-target>        e.g. tools/deploy.sh build-1
#
# Runs on the laptop (macOS bash 3.2 compatible). Builds a wheel into a temp folder,
# copies it with install/install.sh, node.toml.example and systemd/ into
# ~/.mulebox/tmp/ on the target, runs the installer there and prints the installed version.
set -euo pipefail

usage() { printf 'usage: tools/deploy.sh <ssh-target>\n' >&2; exit 2; }
die() { printf 'mulebox deploy: error: %s\n' "$*" >&2; exit 1; }

check_target() {
    case "$1" in
        "" | -*) die "ssh target must not be empty or start with '-': '$1'" ;;
        *[[:space:]]* | *:*) die "ssh target must be a host alias or user@host: '$1'" ;;
    esac
}

pick_python() {  # the repo's .venv python if present, else python3
    if [ -x "$1/.venv/bin/python" ]; then
        printf '%s\n' "$1/.venv/bin/python"
    else
        command -v python3 || die "python3 not found"
    fi
}

build_wheel() {  # repo outdir -> prints the wheel path
    local python wheel
    python="$(pick_python "$1")"
    "$python" -m pip wheel --no-deps --disable-pip-version-check -q -w "$2" "$1" >&2
    for wheel in "$2"/mulebox-*.whl; do
        [ -f "$wheel" ] || die "no wheel was built in $2"
        printf '%s\n' "$wheel"
        return 0
    done
}

main() {
    [ $# -eq 1 ] || usage
    local target="$1" repo outdir wheel name
    check_target "$target"
    repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    outdir="$(mktemp -d "${TMPDIR:-/tmp}/mulebox-deploy.XXXXXX")"

    wheel="$(build_wheel "$repo" "$outdir")"
    name="$(basename "$wheel")"
    case "$name" in
        *[!A-Za-z0-9._+-]*) die "unexpected wheel name: $name" ;;
    esac
    printf 'Built %s\n' "$name"

    ssh -T -- "$target" 'mkdir -p ~/.mulebox/tmp'
    scp -q -r -- "$wheel" "$repo/install/install.sh" "$repo/install/node.toml.example" \
        "$repo/install/systemd" "$target:.mulebox/tmp/"
    rm -f "$wheel"
    rmdir "$outdir" 2>/dev/null || true

    printf 'Installing on %s\n' "$target"
    ssh -T -- "$target" "bash ~/.mulebox/tmp/install.sh ~/.mulebox/tmp/$name"
    printf 'Remote version: '
    # shellcheck disable=SC2088  # the remote shell expands ~
    ssh -T -- "$target" '~/.mulebox/bin/mulebox --version'
}

main "$@"
