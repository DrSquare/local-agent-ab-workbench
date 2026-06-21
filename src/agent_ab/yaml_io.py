"""YAML helpers for human-edited config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class YamlConfigError(ValueError):
    """Raised when a YAML config file cannot be loaded safely."""


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 YAML file whose root must be a mapping."""

    input_path = Path(path)
    if not input_path.exists():
        raise YamlConfigError(f"config file does not exist: {input_path}")
    try:
        payload = yaml.load(input_path.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise YamlConfigError(f"invalid YAML in {input_path}: {exc}") from exc
    if payload is None:
        raise YamlConfigError(f"config file is empty: {input_path}")
    if not isinstance(payload, dict):
        raise YamlConfigError(f"config root must be a mapping/object: {input_path}")
    return payload
