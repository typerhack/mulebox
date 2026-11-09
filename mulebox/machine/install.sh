#!/usr/bin/env bash
# Install or upgrade mulebox on a Linux build machine, for the current user.
#
#   bash install.sh /path/to/mulebox-<version>-py3-none-any.whl
#
# Safe to rerun: an upgrade installs the new wheel and restarts the services.
# Never uses sudo and never deletes a directory: an old venv is moved into
# ~/.mulebox/tmp, and only exact, known temp files are removed. node.toml.example and
# systemd/ must sit next to this script (`mulebox setup` sends them).
# Environment: MULEBOX_PYTHON picks the Python to use (default python3). MULEBOX_COORDINATOR
# (an ssh target) and MULEBOX_COORDINATOR_KEY (an absolute key path) make a new node.toml a
# worker of that coordinator, with no coordinator or dashboard of its own (`setup --worker-of`).
set -euo pipefail

MB_HOME="$HOME/.mulebox"
MB_TMP="$MB_HOME/tmp"
VENV="$MB_HOME/venv"
BIN="$MB_HOME/bin/mulebox"
CONFIG_DIR="$HOME/.config/mulebox"
NODE_TOML="$CONFIG_DIR/node.toml"
UNIT_DIR="$HOME/.config/systemd/user"
# All units are copied. The coordinator, worker and dashboard are enabled here (the
# dashboard runs with the coordinator); the runner template is enabled per runner by
# `mulebox runner add`.
UNITS=(mulebox-coordinator.service mulebox-worker.service mulebox-dashboard.service
       mulebox-runner@.service)
PYTHON="${MULEBOX_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '%s\n' "$*"; }
die() { printf 'mulebox install: error: %s\n' "$*" >&2; exit 1; }

# --- checks ------------------------------------------------------------------------

check_platform() {
    [ "$(uname -s)" = "Linux" ] || die "build machines must run Linux (found $(uname -s))"
    command -v systemctl >/dev/null 2>&1 || die "systemd is required (systemctl not found)"
    systemctl --user show-environment >/dev/null 2>&1 \
        || die "'systemctl --user' does not work; log in through ssh or a desktop session, not su"
    command -v git >/dev/null 2>&1 \
        || die "git is required, as jobs run from a project's repository here; on Ubuntu or Debian: sudo apt-get install git"
}

check_python() {
    command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found; install Python 3.12 or newer"
    "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
        || die "Python 3.12 or newer is required ($PYTHON is $("$PYTHON" -V 2>&1))"
}

python_minor() {  # major.minor of $PYTHON, e.g. 3.12
    "$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])'
}

venv_minor() {  # major.minor the venv was built with, from pyvenv.cfg ("" if none)
    local cfg="$1/pyvenv.cfg"
    [ -f "$cfg" ] || return 0
    sed -n 's/^version[_a-z]* *= *\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$cfg" | head -n 1
}

venv_hint() {
    say "" >&2
    say "Python cannot create virtual environments here. On Ubuntu or Debian run:" >&2
    say "    sudo apt-get install python3-venv" >&2
    say "then run this installer again." >&2
    exit 1
}

check_wheel() {
    [ -f "$1" ] || die "wheel not found: $1"
    case "$1" in *.whl) ;; *) die "not a wheel file: $1" ;; esac
}

# --- venv and package ----------------------------------------------------------------

venv_is_current() {
    [ -x "$VENV/bin/python" ] && [ "$(venv_minor "$VENV")" = "$(python_minor)" ] \
        && "$VENV/bin/python" -m pip --version >/dev/null 2>&1
}

# Build a fresh venv under ~/.mulebox/tmp (this is also the "venv works" check) and swap
# it in with mv. An old venv is moved aside into ~/.mulebox/tmp, never deleted.
make_venv() {
    local new stamp
    new="$(mktemp -d "$MB_TMP/venv-new.XXXXXX")"
    "$PYTHON" -m venv "$new" >/dev/null 2>&1 || venv_hint
    "$new/bin/python" -m pip --version >/dev/null 2>&1 || venv_hint
    if [ -e "$VENV" ] || [ -L "$VENV" ]; then
        stamp="$(date +%Y%m%d-%H%M%S)"
        mv "$VENV" "$MB_TMP/venv-old-$stamp.$$"
        say "Moved the previous venv to $MB_TMP/venv-old-$stamp.$$ (safe to delete)."
    fi
    mv "$new" "$VENV"
    say "Created $VENV with Python $(python_minor)."
}

install_wheel() {
    local pip=("$VENV/bin/python" -m pip --disable-pip-version-check -q)
    # Dependencies first, then force the wheel itself so a rerun with the same version
    # still replaces the files (and writes the entry point for this venv's location).
    "${pip[@]}" install "$1"
    "${pip[@]}" install --no-deps --force-reinstall "$1"
    mkdir -p "$MB_HOME/bin"
    ln -sfn "$VENV/bin/mulebox" "$BIN"
    link_on_path
}

# The same `mulebox` name on a build machine as on the laptop. A real file of that name is
# someone else's, so it stays.
link_on_path() {
    local link="$HOME/.local/bin/mulebox"
    mkdir -p "$HOME/.local/bin"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        say "mulebox install: note: $link is a real file, left alone"
        return 0
    fi
    ln -sfn "$BIN" "$link"
}

# --- node config and roots -----------------------------------------------------------

node_name() {  # short hostname, reduced to the characters a node name may use
    local raw
    raw="$(hostname -s 2>/dev/null || hostname)"
    raw="$(printf '%s' "$raw" | tr -c 'A-Za-z0-9._-' '-')"
    raw="${raw#"${raw%%[A-Za-z0-9]*}"}"
    printf '%s\n' "${raw:-mulebox-node}"
}

render_node_config() {  # template name home -> TOML on stdout
    local text
    # bash >= 5.2 would expand '&' in the replacement; turn that off (no-op on older bash).
    shopt -u patsub_replacement 2>/dev/null || true
    text="$(<"$1")"
    text="${text//@NAME@/$2}"
    text="${text//@HOME@/$3}"
    if [ -n "${MULEBOX_COORDINATOR:-}" ]; then
        case "$MULEBOX_COORDINATOR${MULEBOX_COORDINATOR_KEY:-}" in
            *\"*|*\\*) die "the coordinator address or key path holds a quote or backslash" ;;
        esac
        local worker
        worker="roles = [\"worker\"]"$'\n'"coordinator = \"$MULEBOX_COORDINATOR\""
        [ -n "${MULEBOX_COORDINATOR_KEY:-}" ] && \
            worker+=$'\n'"coordinator_key = \"$MULEBOX_COORDINATOR_KEY\""
        text="${text//roles = \[\"coordinator\", \"worker\"\]/$worker}"
        text="${text//mode = \"local\"/mode = \"off\"}"
    fi
    printf '%s\n' "$text"
}

write_node_config() {
    mkdir -p "$CONFIG_DIR"
    if [ -e "$NODE_TOML" ]; then
        say "Keeping existing $NODE_TOML."
        return 0
    fi
    local draft="$NODE_TOML.new.$$"
    render_node_config "$SCRIPT_DIR/node.toml.example" "$(node_name)" "$HOME" > "$draft"
    if ! node_info "$draft" >/dev/null; then
        rm -f "$draft"
        die "the generated node config did not validate (see above)"
    fi
    mv "$draft" "$NODE_TOML"
    say "Wrote $NODE_TOML (edit it to change roots, slots or capabilities)."
}

# Validate a node.toml with mulebox itself; print "roles <role>..." and "root <path>" lines.
node_info() {
    "$VENV/bin/python" - "$1" <<'PY'
import sys
from pathlib import Path
from mulebox.common.config import ConfigError, load_node_config
try:
    node = load_node_config(Path(sys.argv[1]))
except ConfigError as exc:
    sys.exit(f"mulebox install: error: {exc}")
print("roles", *node.roles)
for path in node.roots.values():
    print("root", path)
PY
}

check_roots() {  # the roots must pass mulebox's own safety checks once they exist
    "$VENV/bin/python" - "$NODE_TOML" <<'PY'
import sys
from pathlib import Path
from mulebox.common.config import load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.roots import Roots
try:
    Roots.from_config(load_node_config(Path(sys.argv[1])).roots)
except MuleboxError as exc:
    sys.exit(f"mulebox install: error: unsafe roots in {sys.argv[1]}: {exc}")
PY
}

ROLES=()
ROOTS=()
read_node_config() {
    local kind rest info
    info="$(node_info "$NODE_TOML")" || die "fix $NODE_TOML and run the installer again"
    ROLES=()
    ROOTS=()
    while read -r kind rest; do
        case "$kind" in
            roles) read -r -a ROLES <<<"$rest" ;;
            root) ROOTS+=("$rest") ;;
        esac
    done <<<"$info"
}

make_roots() {
    local root
    for root in "${ROOTS[@]}"; do
        mkdir -p "$root"
        chmod 750 "$root"
    done
    check_roots
}

# --- services --------------------------------------------------------------------------

has_role() {
    local role
    for role in "${ROLES[@]}"; do [ "$role" = "$1" ] && return 0; done
    return 1
}

wanted_units() {
    has_role coordinator && printf '%s\n' mulebox-coordinator.service mulebox-dashboard.service
    has_role worker && printf '%s\n' mulebox-worker.service
    return 0
}

install_units() {
    local unit
    mkdir -p "$UNIT_DIR"
    for unit in "${UNITS[@]}"; do
        cp "$SCRIPT_DIR/systemd/$unit" "$UNIT_DIR/$unit.new.$$"
        chmod 644 "$UNIT_DIR/$unit.new.$$"
        mv "$UNIT_DIR/$unit.new.$$" "$UNIT_DIR/$unit"
    done
    systemctl --user daemon-reload
    # A runner may be in a job: its new CPU share is set in place, never by a restart.
    systemctl --user list-units --plain --no-legend 'mulebox-runner@*' 2>/dev/null \
        | awk '{print $1}' | while read -r unit; do
            if [ -n "$unit" ]; then
                systemctl --user set-property --runtime "$unit" \
                    CPUWeight=50 IOWeight=50 2>/dev/null || true
            fi
        done
}

start_units() {
    local unit
    while read -r unit; do
        [ -n "$unit" ] || continue
        if systemctl --user is-active --quiet "$unit"; then
            systemctl --user enable --quiet "$unit"
            systemctl --user restart "$unit"
            say "Restarted $unit."
        else
            systemctl --user enable --now --quiet "$unit"
            say "Enabled and started $unit."
        fi
    done < <(wanted_units)
}

check_linger() {
    local user linger
    user="${USER:-$(id -un)}"
    linger="$(loginctl show-user "$user" -p Linger 2>/dev/null || true)"
    if [ "${linger#Linger=}" = "no" ] && ! loginctl --no-ask-password enable-linger "$user" 2>/dev/null; then
        say ""
        say "Lingering is off for $user, so the mulebox services stop when you log out."
        say "To keep them running after logout (and start them at boot), run once:"
        say "    sudo loginctl enable-linger $user"
    fi
}

summary() {
    local unit
    say ""
    say "mulebox installed: $("$BIN" --version)"
    say "  command:  $BIN"
    say "  venv:     $VENV"
    say "  config:   $NODE_TOML"
    say "  roots:    ${ROOTS[*]}"
    while read -r unit; do
        [ -n "$unit" ] || continue
        say "  service:  $unit ($(systemctl --user is-active "$unit" 2>/dev/null || true))"
    done < <(wanted_units)
    say "Logs: journalctl --user -u mulebox-worker -u mulebox-coordinator"
}

main() {
    [ $# -eq 1 ] || { say "usage: bash install.sh <mulebox wheel>" >&2; exit 2; }
    local wheel
    check_wheel "$1"
    wheel="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    check_platform
    check_python
    [ -d "$MB_HOME" ] || mkdir -m 750 "$MB_HOME"
    mkdir -p "$MB_TMP"
    if venv_is_current; then
        say "Reusing $VENV (Python $(python_minor))."
    else
        make_venv
    fi
    install_wheel "$wheel"
    write_node_config
    read_node_config
    make_roots
    install_units
    start_units
    summary
    check_linger
}

# Run main unless sourced (the tests source this file to call single functions).
if ! (return 0 2>/dev/null); then
    main "$@"
fi
