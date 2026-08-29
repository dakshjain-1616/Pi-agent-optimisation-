"""Pi installed from a local checkout instead of npm — for A/B-ing your own changes.

    -a pi_local:PiLocal --ak src=/path/to/pi-checkout

`src` is either a package dir (npm pack runs on it, once per job) or a prebuilt
.tgz. Everything else — flags, model handling, cost accounting — is inherited.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import override

from harbor.agents.installed.node_install import nvm_node_install_snippet
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment

_lock = asyncio.Lock()
_packed: dict[Path, Path] = {}


async def _tarball(src: Path) -> Path:
    if src.suffix == ".tgz":
        return src
    async with _lock:  # install() runs per trial; pack once
        if src not in _packed:
            out = subprocess.run(
                ["npm", "pack", "--silent", "--pack-destination", str(src)],
                cwd=src, capture_output=True, text=True, check=True,
            ).stdout.strip().splitlines()[-1]
            _packed[src] = src / out
    return _packed[src]


class PiLocal(Pi):
    def __init__(self, *args, src: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._src = Path(src).expanduser().resolve()
        if not self._src.exists():
            raise ValueError(f"src not found: {self._src}")

    @staticmethod
    @override
    def name() -> str:
        return "pi-local"  # keeps it a separate eval key from stock `pi`

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        tgz = await _tarball(self._src)
        await self.ensure_system_dependencies(environment, ("curl",))
        await self._upload_agent_owned_file(environment, tgz, "/tmp/pi-local.tgz")
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet()} && "
                "npm install -g --ignore-scripts /tmp/pi-local.tgz && pi --version"
            ),
        )
