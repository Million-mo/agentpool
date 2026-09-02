"""Unit tests for ``UriSchemeRegistry`` ownership semantics.

A URI scheme is owned by at most one provider *type*. Re-registering a
scheme with another instance of the same provider type (e.g. a capability
configured per-agent, like ``VikingCapability``) is idempotent — the first
instance keeps ownership. A genuinely different provider type claiming an
already-owned scheme raises ``UriSchemeConflictError``.

Regression coverage: a manifest with multiple agents each declaring a
``type: viking`` capability crashed at pool init on agentpool main
(``UriSchemeConflictError: URI scheme 'viking' is already claimed by
'VikingCapability'``). These tests pin the intended semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from wolfharness import AgentsManifest, NativeAgentConfig
from wolfharness.capabilities.resource_protocols import (
    BlobResourceContent,
    ResourceEntry,
    TextResourceContent,
    UriSchemeConflictError,
)
from wolfharness.capabilities.uri_scheme_registry import UriSchemeRegistry
from wolfharness_config.capabilities import build_config_capabilities


if TYPE_CHECKING:
    from collections.abc import Sequence


pytestmark = pytest.mark.unit


class _AlphaProvider:
    """Fake provider type A claiming the ``custom`` scheme."""

    owned_schemes: frozenset[str] = frozenset({"custom"})

    async def list_resources(self) -> Sequence[ResourceEntry]:
        return []

    async def read_resource(
        self, uri: str
    ) -> list[TextResourceContent | BlobResourceContent] | None:
        return None

    async def resource_exists(self, uri: str) -> bool:
        return False


class _BetaProvider(_AlphaProvider):
    """Fake provider type B claiming the ``custom`` scheme (conflicting type)."""


class _GammaProvider(_AlphaProvider):
    """Fake provider type C claiming the ``other`` scheme (no overlap)."""

    owned_schemes: frozenset[str] = frozenset({"other"})


class _VikingSchemeFake(_AlphaProvider):
    """Fake provider type claiming the ``viking`` scheme (foreign type)."""

    owned_schemes: frozenset[str] = frozenset({"viking"})


def _registry_with_alpha() -> tuple[UriSchemeRegistry, _AlphaProvider]:
    registry = UriSchemeRegistry()
    alpha = _AlphaProvider()
    registry.register("AlphaProvider", alpha.owned_schemes, alpha)
    return registry, alpha


class TestRegistration:
    """Registration, lookup, and introspection basics."""

    def test_registration_and_lookup(self) -> None:
        registry, alpha = _registry_with_alpha()

        assert registry.owner_of("custom") == "AlphaProvider"
        assert registry.lookup("custom") is alpha
        assert registry.registered_schemes() == frozenset({"custom"})
        assert registry.registered_providers() == [alpha]

    def test_unknown_scheme_returns_none(self) -> None:
        registry, _ = _registry_with_alpha()

        assert registry.lookup("missing") is None
        assert registry.owner_of("missing") is None


class TestSameTypeIdempotency:
    """Same-type re-registration is a no-op that keeps the first owner."""

    def test_same_type_re_registration_is_idempotent(self) -> None:
        registry, alpha = _registry_with_alpha()
        second_alpha = _AlphaProvider()

        # Same provider type re-claiming the scheme must not raise.
        registry.register("AlphaProvider", second_alpha.owned_schemes, second_alpha)

        # First claimant keeps ownership.
        assert registry.owner_of("custom") == "AlphaProvider"
        assert registry.lookup("custom") is alpha
        assert registry.registered_providers() == [alpha]

    def test_re_registration_of_same_instance_is_idempotent(self) -> None:
        registry, alpha = _registry_with_alpha()

        registry.register("AlphaProvider", alpha.owned_schemes, alpha)

        assert registry.lookup("custom") is alpha
        assert registry.owner_of("custom") == "AlphaProvider"


class TestDifferentTypeConflict:
    """A different provider type claiming an owned scheme still raises."""

    def test_different_type_conflict_raises(self) -> None:
        registry, _ = _registry_with_alpha()
        beta = _BetaProvider()

        with pytest.raises(UriSchemeConflictError) as exc_info:
            registry.register("BetaProvider", beta.owned_schemes, beta)

        assert exc_info.value.scheme == "custom"
        assert exc_info.value.existing_provider == "AlphaProvider"
        assert exc_info.value.conflicting_provider == "BetaProvider"

    def test_conflict_does_not_partially_commit(self) -> None:
        registry, alpha = _registry_with_alpha()
        beta = _BetaProvider()

        with pytest.raises(UriSchemeConflictError):
            # ``other`` is free, but ``custom`` conflicts — nothing may be
            # committed once the first conflicting scheme is detected.
            registry.register("BetaProvider", frozenset({"custom", "other"}), beta)

        assert registry.lookup("custom") is alpha
        assert registry.lookup("other") is None
        assert registry.registered_schemes() == frozenset({"custom"})

    def test_non_conflicting_type_registers_alongside(self) -> None:
        registry, _ = _registry_with_alpha()
        gamma = _GammaProvider()

        registry.register("GammaProvider", gamma.owned_schemes, gamma)

        assert registry.owner_of("custom") == "AlphaProvider"
        assert registry.owner_of("other") == "GammaProvider"
        assert registry.registered_schemes() == frozenset({"custom", "other"})


class TestUnregister:
    """Unregistering a provider releases its schemes."""

    def test_unregister_releases_scheme(self) -> None:
        registry, alpha = _registry_with_alpha()
        gamma = _GammaProvider()
        registry.register("GammaProvider", gamma.owned_schemes, gamma)

        registry.unregister(alpha)

        assert registry.lookup("custom") is None
        assert registry.owner_of("custom") is None
        # Other owners are untouched.
        assert registry.owner_of("other") == "GammaProvider"


MULTI_VIKING_YAML = """\
agents:
  engineer:
    type: native
    model: openai:gpt-4o-mini
    capabilities:
      - type: viking
        enable_memory: true
        support_vision: false
  vision_worker:
    type: native
    model: openai:gpt-4o-mini
    capabilities:
      - type: viking
        support_vision: true
  research_agent:
    type: native
    model: openai:gpt-4o-mini
    capabilities:
      - type: viking
        enable_memory: false
"""


class TestVikingCapabilityRegression:
    """Regression: multiple per-agent ``type: viking`` capabilities coexist.

    Mirrors the exact registration loop in
    ``AgentFactory.register_config_capabilities``: build each agent's config
    capabilities and register their owned schemes into a shared registry.
    Before the same-type idempotency fix this raised
    ``UriSchemeConflictError`` on the second agent.
    """

    def _register_manifest_capabilities(self) -> tuple[UriSchemeRegistry, list[object]]:
        manifest = AgentsManifest.from_yaml(MULTI_VIKING_YAML)
        registry = UriSchemeRegistry()
        all_caps: list[object] = []
        for agent in manifest.agents.values():
            assert isinstance(agent, NativeAgentConfig)
            assert agent.capabilities is not None
            config_caps = build_config_capabilities(agent.capabilities)
            for cap in config_caps:
                owned: frozenset[str] = getattr(cap, "owned_schemes", frozenset())
                if owned:
                    registry.register(type(cap).__name__, owned, cap)
                all_caps.append(cap)
        return registry, all_caps

    def test_multiple_viking_capabilities_share_scheme(self) -> None:
        registry, all_caps = self._register_manifest_capabilities()

        assert len(all_caps) == 3
        assert registry.owner_of("viking") == "VikingCapability"
        first = all_caps[0]
        assert registry.lookup("viking") is first
        # Per-agent behavior is preserved on the individual instances.
        assert [getattr(cap, "support_vision", None) for cap in all_caps] == [
            False,
            True,
            None,
        ]

    def test_different_type_claiming_viking_still_conflicts(self) -> None:
        registry, _ = self._register_manifest_capabilities()
        beta = _VikingSchemeFake()

        with pytest.raises(UriSchemeConflictError):
            registry.register("BetaProvider", beta.owned_schemes, beta)
