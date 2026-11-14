"""Inside an isolated compose job: `localhost:$MULEBOX_PORT_...` reaches the service again.

    python3 port_forward.py 127.0.0.1:41234=db:5432 [...]

A compose job's services publish their ports on the node's loopback, which a job in its own
container cannot reach; it reaches them by service name. Projects follow the docs and read
`MULEBOX_PORT_<SERVICE>_<PORT>` with localhost, so this listens there inside the container and
passes each connection on to the service's own port. TCP only. It is mounted read-only into
the job's container (isolated.py) and runs with the image's Python: the standard library only,
nothing of mulebox.
"""

from __future__ import annotations

import asyncio
import sys


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


def _handler(host: str, port: int):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(host, port)
        except OSError:
            writer.close()
            return
        await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
    return handle


def parse(spec: str) -> tuple[str, int, str, int]:
    listen, _, target = spec.partition("=")
    lhost, _, lport = listen.rpartition(":")
    thost, _, tport = target.rpartition(":")
    if not (lhost and lport.isdigit() and thost and tport.isdigit()):
        raise ValueError(f"not LISTEN_HOST:PORT=HOST:PORT: {spec!r}")
    return lhost, int(lport), thost, int(tport)


async def serve(specs: list[str]) -> None:
    servers = []
    for spec in specs:
        lhost, lport, thost, tport = parse(spec)
        servers.append(await asyncio.start_server(_handler(thost, tport), lhost, lport))
    print("mulebox: localhost ports forwarded to their services", flush=True)
    await asyncio.gather(*(server.serve_forever() for server in servers))


def main(argv: list[str]) -> int:
    try:
        asyncio.run(serve(argv))
    except (ValueError, OSError) as exc:
        print(f"mulebox: port forward: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
