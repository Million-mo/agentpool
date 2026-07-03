"""Capability configuration models for YAML-based capability wiring.

Supports two config styles:

1. **Typed config** (recommended): uses a discriminator field ``type`` with
   predefined config models for the 6 built-in capabilities.
2. **Import-path config**: uses a dotted import path string to load any
   ``AbstractCapability`` subclass, with arbitrary ``args``.

Example YAML::

    agents:
      my_agent:
        capabilities:
          - type: loop_detection
            max_depth: 10
          - type: token_budget
            budget: 50000
          - type: agentpool.capabilities.memory.MemoryCapability
            args:
              max_memories: 100
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from schemez import Schema


class LoopDetectionCapabilityConfig(Schema):
    """Config for ``LoopDetectionCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Loop Detection"})

    type: Literal["loop_detection"] = Field("loop_detection", init=False)
    max_depth: int = Field(default=25, title="Max delegation depth")


class TokenBudgetCapabilityConfig(Schema):
    """Config for ``TokenBudgetCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Token Budget"})

    type: Literal["token_budget"] = Field("token_budget", init=False)
    budget: int = Field(default=100_000, title="Token budget per run")


class ToolOutputBudgetCapabilityConfig(Schema):
    """Config for ``ToolOutputBudgetCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Tool Output Budget"})

    type: Literal["tool_output_budget"] = Field("tool_output_budget", init=False)
    max_output_chars: int = Field(default=10_000, title="Max chars per tool output")


class DynamicContextCapabilityConfig(Schema):
    """Config for ``DynamicContextCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Dynamic Context"})

    type: Literal["dynamic_context"] = Field("dynamic_context", init=False)
    max_history_messages: int = Field(default=20, title="Max messages before compaction")


class SkillActivationCapabilityConfig(Schema):
    """Config for ``SkillActivationCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Skill Activation"})

    type: Literal["skill_activation"] = Field("skill_activation", init=False)
    max_skills: int = Field(default=10, title="Max skills to inject")


class MemoryCapabilityConfig(Schema):
    """Config for ``MemoryCapability``."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Memory"})

    type: Literal["memory"] = Field("memory", init=False)
    max_memories: int = Field(default=50, title="Max memories to store")


class ImportPathCapabilityConfig(BaseModel):
    """Config for loading any capability by import path.

    Uses a dotted Python import path to load an ``AbstractCapability``
    subclass and instantiate it with ``args``.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str
    """Import path to the capability class
    (e.g. ``agentpool.capabilities.memory.MemoryCapability``)."""

    args: dict[str, Any] = Field(default_factory=dict)
    """Arguments to pass to the capability constructor."""

    def build(self) -> Any:
        """Import and instantiate the capability.

        Raises:
            ImportError: If the module cannot be imported.
            ValueError: If the type path is invalid or the class not found.
        """
        try:
            module_path, class_name = self.type.rsplit(".", 1)
        except ValueError:
            msg = f"Invalid capability type path: {self.type!r}"
            raise ValueError(msg) from None

        try:
            module = __import__(module_path, fromlist=[class_name])
        except ImportError as e:
            msg = f"Cannot import module for capability {self.type!r}: {e}"
            raise ImportError(msg) from e

        try:
            cls = getattr(module, class_name)
        except AttributeError:
            msg = f"Class {class_name!r} not found in module {module_path!r}"
            raise ValueError(msg) from None

        return cls(**self.args)


CapabilityConfig = Annotated[
    LoopDetectionCapabilityConfig
    | TokenBudgetCapabilityConfig
    | ToolOutputBudgetCapabilityConfig
    | DynamicContextCapabilityConfig
    | SkillActivationCapabilityConfig
    | MemoryCapabilityConfig
    | ImportPathCapabilityConfig,
    Field(union_mode="smart"),
]
"""Union of all capability config types.

Uses ``union_mode='smart'`` instead of a discriminator because
``ImportPathCapabilityConfig.type`` is a free-form string (import path),
not a fixed literal."""

_capability_config_adapter: TypeAdapter[Any] = TypeAdapter(CapabilityConfig)


def parse_capability_config(data: dict[str, Any] | BaseModel) -> Any:
    """Parse a dict or model into the correct ``CapabilityConfig`` subtype.

    Uses Pydantic's smart union mode to dispatch to the right config model
    based on the ``type`` field value.
    """
    if isinstance(data, BaseModel):
        return data
    return _capability_config_adapter.validate_python(data)


_TYPED_CAPABILITY_MAP: dict[str, tuple[str, str]] = {
    "loop_detection": ("agentpool.capabilities.loop_detection", "LoopDetectionCapability"),
    "token_budget": ("agentpool.capabilities.token_budget", "TokenBudgetCapability"),
    "tool_output_budget": (
        "agentpool.capabilities.tool_output_budget",
        "ToolOutputBudgetCapability",
    ),
    "dynamic_context": ("agentpool.capabilities.dynamic_context", "DynamicContextCapability"),
    "skill_activation": ("agentpool.capabilities.skill_activation", "SkillActivationCapability"),
    "memory": ("agentpool.capabilities.memory", "MemoryCapability"),
}
"""Maps typed capability config ``type`` values to (module_path, class_name)."""


def build_capability(config: Any) -> Any:
    """Create a capability instance from its config model.

    Handles three input types:

    1. **ImportPathCapabilityConfig** — calls ``.build()`` to import and instantiate.
    2. **Typed config models** (LoopDetection, TokenBudget, etc.) — looks up the
       capability class via ``_TYPED_CAPABILITY_MAP`` and constructs it from the
       config's fields (excluding ``type``).
    3. **Pre-instantiated capabilities** — returned as-is (passthrough for objects
       that are already ``AbstractCapability`` instances).

    Args:
        config: A capability config model or a pre-instantiated capability.

    Returns:
        A capability instance.

    Raises:
        ValueError: If the config type is unknown.
        ImportError: If the capability module cannot be imported.
    """
    if isinstance(config, ImportPathCapabilityConfig):
        return config.build()

    if isinstance(config, LoopDetectionCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["loop_detection"]
    elif isinstance(config, TokenBudgetCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["token_budget"]
    elif isinstance(config, ToolOutputBudgetCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["tool_output_budget"]
    elif isinstance(config, DynamicContextCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["dynamic_context"]
    elif isinstance(config, SkillActivationCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["skill_activation"]
    elif isinstance(config, MemoryCapabilityConfig):
        entry = _TYPED_CAPABILITY_MAP["memory"]
    else:
        # Passthrough: already a capability instance or unknown object.
        return config

    module_path, class_name = entry
    from importlib import import_module

    mod = import_module(module_path)
    cls = getattr(mod, class_name)

    kwargs = {k: v for k, v in config.model_dump().items() if k != "type"}
    return cls(**kwargs)
