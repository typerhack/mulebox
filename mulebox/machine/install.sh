#!/usr/bin/env bash
# Install or upgrade mulebox on a node (Linux with systemd, or macOS), for the current user.
#
#   bash install.sh /path/to/mulebox-<version>-py3-none-any.whl
#
# Safe to rerun: an upgrade installs the new wheel and restarts the services.
# Never uses sudo and never deletes a directory: an old venv is moved into
# ~/.mulebox/tmp, and only exact, known temp files are removed. node.toml.example must sit
# next to this script (`mulebox setup` sends it). The services (systemd units or launchd agents)
# are mulebox's own: `mulebox service install` writes and starts them (mulebox/services/).
# Runs on the bash a Mac has (3.2), so nothing newer than that is used.
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
PYTHON="${MULEBOX_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '%s\n' "$*"; }
die() { printf 'mulebox install: error: %s\n' "$*" >&2; exit 1; }

# --- checks ------------------------------------------------------------------------

OS="$(uname -s)"

check_platform() {
    case "$OS" in
        Linux)
            command -v systemctl >/dev/null 2>&1 || die "systemd is required (systemctl not found)"
            systemctl --user show-environment >/dev/null 2>&1 \
                || die "'systemctl --user' does not work; log in through ssh or a desktop session, not su"
            git --version >/dev/null 2>&1 \
                || die "git is required, as jobs run from a project's repository here; on Ubuntu or Debian: sudo apt-get install git"
            ;;
        Darwin)
            # An ssh login reads no shell profile, so Homebrew's folders are not on PATH yet.
            PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
            export PATH
            # /usr/bin/git is there even without git: it only offers to install the tools.
            git --version >/dev/null 2>&1 \
                || die "git is required, as jobs run from a project's repository here; on the Mac: xcode-select --install"
            ;;
        *) die "nodes run Linux or macOS (found $OS)" ;;
    esac
}

check_python() {
    local how="install Python 3.12 or newer"
    [ "$OS" = "Darwin" ] && how="$how, such as with Homebrew: brew install python@3.13"
    command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found; $how"
    "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
        || die "Python 3.12 or newer is required ($PYTHON is $("$PYTHON" -V 2>&1)); $how"
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

# The same `mulebox` name on a node as on the dev machine. A real file of that name is
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

# Validate a node.toml with mulebox itself; print a "root <path>" line per root.
node_info() {
    "$VENV/bin/python" - "$1" <<'PY'
import sys
from pathlib import Path
from mulebox.common.config import ConfigError, load_node_config
try:
    node = load_node_config(Path(sys.argv[1]))
except ConfigError as exc:
    sys.exit(f"mulebox install: error: {exc}")
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

ROOTS=()
read_node_config() {  # the roles are read by `mulebox service install` itself
    local kind rest info
    info="$(node_info "$NODE_TOML")" || die "fix $NODE_TOML and run the installer again"
    ROOTS=()
    while read -r kind rest; do
        [ "$kind" = "root" ] && ROOTS+=("$rest")
    done <<<"$info"
    return 0
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

install_services() {  # systemd units or launchd agents, by mulebox itself (mulebox/services/)
    "$BIN" service install --config "$NODE_TOML" || die "the services did not start (see above)"
}

summary() {
    say ""
    say "mulebox installed: $("$BIN" --version)"
    say "  command:  $BIN"
    say "  venv:     $VENV"
    say "  config:   $NODE_TOML"
    say "  roots:    ${ROOTS[*]}"
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
    summary
    install_services
}

# Run main unless sourced (the tests source this file to call single functions).
if ! (return 0 2>/dev/null); then
    main "$@"
fi
