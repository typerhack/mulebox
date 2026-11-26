#!/usr/bin/env bash
# The venv steps of install.sh, which sources this file from its own folder: each install builds a
# venv of its own under ~/.mulebox/venvs and swaps it in with one rename of the ~/.mulebox/venv
# link, so a power cut at any moment leaves a whole mulebox (docs/design.md, Sudden power loss).
# Uses install.sh's MB_HOME, VENV, VENVS, BIN, PYTHON, say, python_minor and link_on_path.
# Runs on the bash a Mac has (3.2).
set -euo pipefail

VENV="$MB_HOME/venv"  # a link to the venv in use, in VENVS
VENVS="$MB_HOME/venvs"
NEW_VENV=""  # the venv this install builds
PREVIOUS_VENV=""  # the one in use before it, kept
SWAPPED=""  # set while the new venv is in use but not yet through its trial (roll_back)

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

venv_is_current() {
    [ -x "$VENV/bin/python" ] && [ "$(venv_minor "$VENV")" = "$(python_minor)" ] \
        && "$VENV/bin/python" -m pip --version >/dev/null 2>&1
}

# A venv of this install's own, beside the one in use: a copy of it when its Python is the same,
# so the dependencies it has need no download, else a new one.
new_venv() {
    mkdir -p "$VENVS"
    NEW_VENV="$VENVS/$(date +%Y%m%d-%H%M%S)-$$"
    if venv_is_current; then
        cp -pPR "$VENV/" "$NEW_VENV"
        say "Copied the venv in use to $NEW_VENV."
    else
        "$PYTHON" -m venv "$NEW_VENV" >/dev/null 2>&1 || venv_hint
        say "Created $NEW_VENV with Python $(python_minor)."
    fi
    "$NEW_VENV/bin/python" -m pip --version >/dev/null 2>&1 || venv_hint
}

install_wheel() {
    local pip=("$NEW_VENV/bin/python" -m pip --disable-pip-version-check -q)
    # Dependencies first, then force the wheel itself so a rerun with the same version
    # still replaces the files (and writes the entry point for this venv's location).
    "${pip[@]}" install "$1"
    "${pip[@]}" install --no-deps --force-reinstall "$1"
}

# What the venv link points to now, as a name in VENVS ("" for none).
venv_in_use() {
    [ -L "$VENV" ] || return 0
    basename "$(readlink "$VENV")"
}

# Put the new venv in use with one rename of the link, once it is on disk. A venv from before
# 1.47 is a real folder: it is moved into VENVS first, the one moment a cut could leave none.
swap_venv() {
    local link="$MB_HOME/venv.next.$$"
    sync
    PREVIOUS_VENV="$(venv_in_use)"
    if [ -d "$VENV" ] && [ ! -L "$VENV" ]; then
        PREVIOUS_VENV="$(date +%Y%m%d-%H%M%S)-old"
        mv "$VENV" "$VENVS/$PREVIOUS_VENV"
    fi
    ln -s "venvs/$(basename "$NEW_VENV")" "$link"
    "$NEW_VENV/bin/python" -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$link" "$VENV"
    sync
    SWAPPED=1
    mkdir -p "$MB_HOME/bin"
    ln -sfn "$VENV/bin/mulebox" "$BIN"
    link_on_path
}

# Put the venv in use before this install back, the same way, and restart its own services:
# an upgrade that failed once its venv was in use, or did not hold through its trial (M23.7).
roll_back() {
    local link="$MB_HOME/venv.back.$$" back="$VENVS/$PREVIOUS_VENV"
    # shellcheck disable=SC2034  # read by install.sh's undo_on_failure
    SWAPPED=""
    if [ -z "$PREVIOUS_VENV" ] || [ ! -x "$back/bin/python" ]; then
        say "mulebox install: there is no earlier version to go back to" >&2
        return 1
    fi
    ln -s "venvs/$PREVIOUS_VENV" "$link"
    "$back/bin/python" -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$link" "$VENV"
    sync
    say "mulebox install: went back to $("$BIN" --version 2>/dev/null || echo "$PREVIOUS_VENV")" >&2
    if ! "$BIN" service install --config "$NODE_TOML" >&2; then
        say "mulebox install: the earlier version's services did not start either (see above)" >&2
        return 1
    fi
}

# Remove this installer's own old venvs, keeping the one in use and the one before it (an
# upgrade on trial can go back to it): only folders in VENVS named as new_venv names them.
prune_venvs() {
    local path name current
    current="$(venv_in_use)"
    for path in "$VENVS"/*; do
        name="$(basename "$path")"
        if [ ! -d "$path" ] || [ -L "$path" ]; then
            continue
        fi
        if [ "$name" = "$current" ] || [ "$name" = "$PREVIOUS_VENV" ]; then
            continue
        fi
        printf '%s\n' "$name" | grep -Eq '^[0-9]{8}-[0-9]{6}-[0-9a-z]+$' || continue
        rm -rf -- "$path"  # the installer's one recursive delete (tests/install/test_scripts.py)
    done
}
