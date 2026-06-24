from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentpool.resource_providers.skills_instruction import SkillsInstructionProvider


class _Skill:
    disable_model_invocation = False
    user_invocable = True
    context = None
    agent = None
    argument_hint = None
    skill_path = "/skills"

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description


class _Provider:
    async def get_skills(self):
        return [
            _Skill("diagnosis-planning", "Diagnosis planning"),
            _Skill("fta-review", "FTA review"),
        ]


class _Pool:
    @staticmethod
    def is_skill_visible_to_node(skill, node_name):
        if node_name == "rebuttal_agent":
            return True
        return skill.name != "fta-review"


@pytest.mark.unit
async def test_skills_instruction_provider_filters_by_node_package_scope():
    provider = SkillsInstructionProvider(
        skill_provider=_Provider(),
        injection_mode="metadata",
    )
    instruction_func = (await provider.get_instructions())[0]
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            pool=_Pool(),
            node=SimpleNamespace(name="librarian", tools=None),
        ),
    )

    result = await instruction_func(ctx)

    assert "diagnosis-planning" in result
    assert "fta-review" not in result
