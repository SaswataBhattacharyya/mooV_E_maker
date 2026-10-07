from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderArtifact:
    provider: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ProviderRuntimeError(RuntimeError):
    pass


class OptionalProvider:
    name = "provider"

    def analyze(self, image_path: Path, context: dict[str, Any]) -> ProviderArtifact:
        return ProviderArtifact(provider=self.name)

