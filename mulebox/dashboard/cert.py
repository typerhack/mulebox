"""The `lan` mode HTTPS certificate: one self-signed certificate for one address.

Phones only offer full trust to a certificate marked as a CA, so it is one, and name
constraints make it valid for this address alone: if its key ever leaked, it could not
vouch for any other site. Uses the `openssl` command, so there is no new Python
dependency. 825 days is the longest validity Apple accepts for a TLS certificate.
"""

from __future__ import annotations

import ssl
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from mulebox.dashboard.lanfiles import LanNotReady, ensure_private_dir

CERT_NAME = "cert.pem"
KEY_NAME = "key.pem"
VALID_DAYS = 825
_SETUP = "run `mulebox dashboard cert`"
Run = Callable[..., subprocess.CompletedProcess]


def _openssl(run: Run, *args: str) -> subprocess.CompletedProcess:
    try:
        return run(["openssl", *args], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise LanNotReady("the `openssl` command is needed; install the openssl package"
                          ) from None


def generate_argv(address: str, key: Path, cert: Path) -> list[str]:
    extensions = (f"subjectAltName=IP:{address}", "extendedKeyUsage=serverAuth",
                  "basicConstraints=critical,CA:TRUE,pathlen:0",
                  "keyUsage=critical,digitalSignature,keyCertSign",
                  f"nameConstraints=critical,permitted;IP:{address}/255.255.255.255")
    argv = ["req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-nodes", "-keyout", str(key), "-out", str(cert), "-days", str(VALID_DAYS),
            "-subj", f"/CN=mulebox dashboard {address}"]
    for extension in extensions:
        argv += ["-addext", extension]
    return argv


def generate(directory: Path, address: str, *, run: Run = subprocess.run) -> Path:
    """Create the key and certificate, replacing both together. Returns the certificate."""
    ensure_private_dir(directory)
    with tempfile.TemporaryDirectory(dir=directory, prefix=".cert-") as temp:
        key, cert = Path(temp) / KEY_NAME, Path(temp) / CERT_NAME
        done = _openssl(run, *generate_argv(address, key, cert))
        if done.returncode != 0:
            raise LanNotReady(f"openssl could not create the certificate: "
                              f"{done.stderr.strip()[-300:]}")
        key.chmod(0o600)
        cert.chmod(0o644)
        key.replace(directory / KEY_NAME)
        cert.replace(directory / CERT_NAME)
    return directory / CERT_NAME


def fingerprint(cert: Path, *, run: Run = subprocess.run) -> str:
    """The SHA-256 fingerprint, to compare when trusting the certificate on a device."""
    done = _openssl(run, "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256")
    return done.stdout.strip().partition("=")[2]


def check(directory: Path, address: str, *, run: Run = subprocess.run) -> None:
    """Raise LanNotReady unless the certificate exists, is current and fits `address`."""
    cert, key = directory / CERT_NAME, directory / KEY_NAME
    if not cert.is_file() or not key.is_file():
        raise LanNotReady(f"no dashboard certificate yet; {_SETUP}")
    match = _openssl(run, "x509", "-in", str(cert), "-noout", "-checkip", address)
    if "does match" not in match.stdout:
        raise LanNotReady(f"the certificate is not for {address}; {_SETUP} --force")
    current = _openssl(run, "x509", "-in", str(cert), "-noout", "-checkend", "0")
    if current.returncode != 0:
        raise LanNotReady(f"the certificate has expired; {_SETUP} --force")


def server_context(directory: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(directory / CERT_NAME, directory / KEY_NAME)
    return context
