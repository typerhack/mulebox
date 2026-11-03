"""Open the coordinator's store and staging from a build machine's NodeConfig."""

from pathlib import Path

from mulebox.common.config import NodeConfig
from mulebox.common.safepath import Roots
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store


def open_local(node: NodeConfig) -> tuple[Store, Staging]:
    """(open Store, Staging) under the node's `staging` root. Caller closes the store."""
    roots = Roots.from_config(node.roots)
    staging = Staging(roots, Path(node.roots["staging"]))
    return Store(staging.db_path).open(), staging
