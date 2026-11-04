"""Open the coordinator's store and staging from a build machine's NodeConfig."""

from pathlib import Path

from mulebox.common.config import NodeConfig
from mulebox.common.safepath import Roots
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store


def open_local(node: NodeConfig, readonly: bool = False) -> tuple[Store, Staging]:
    """(open Store, Staging) under the node's `staging` root. Caller closes the store.

    `readonly` opens the existing database read-only (the dashboard); it fails when the
    coordinator has not created it yet.
    """
    roots = Roots.from_config(node.roots)
    staging = Staging(roots, Path(node.roots["staging"]))
    return Store(staging.db_path, readonly=readonly).open(), staging
