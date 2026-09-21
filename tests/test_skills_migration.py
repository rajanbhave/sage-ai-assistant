"""Migration verification tests for the Dynamic Skills System.

Verifies that existing skill content was correctly migrated to the
Agent Skills specification format (per-skill directories with SKILL.md)
and that the Strands AgentSkills plugin integrates correctly.
"""

from pathlib import Path

from strands import AgentSkills, Skill

_SKILLS_DIR = Path(__file__).parent.parent / "skills"
_PROMPTS_DIR = Path(__file__).parent.parent / "agent" / "prompts"


class TestSkillFileMigration:
    """Verify skill files parse correctly after migration."""

    def test_claims_workflow_parses(self) -> None:
        """Claims workflow SKILL.md parses with expected name and description."""
        skill = Skill.from_file(_SKILLS_DIR / "claims-workflow")
        assert skill.name == "claims-workflow"
        assert "claims" in skill.description.lower()
        assert len(skill.instructions) > 0

    def test_premium_formulas_parses(self) -> None:
        """Premium formulas SKILL.md parses with expected name and description."""
        skill = Skill.from_file(_SKILLS_DIR / "premium-formulas")
        assert skill.name == "premium-formulas"
        assert "premium" in skill.description.lower()
        assert len(skill.instructions) > 0

    def test_skill_names_are_hyphenated(self) -> None:
        """Skill names follow hyphenated format per Agent Skills spec."""
        skills = Skill.from_directory(_SKILLS_DIR)
        for skill in skills:
            assert "_" not in skill.name, (
                f"Skill name {skill.name!r} uses underscores; "
                f"should be hyphenated per Agent Skills spec"
            )
            assert skill.name == skill.name.lower(), (
                f"Skill name {skill.name!r} is not lowercase"
            )

    def test_claims_workflow_content_preserved(self) -> None:
        """Claims workflow instructions contain key domain content."""
        skill = Skill.from_file(_SKILLS_DIR / "claims-workflow")
        assert "CLM-" in skill.instructions
        assert "SLA" in skill.instructions
        assert "motor_collision" in skill.instructions

    def test_premium_formulas_content_preserved(self) -> None:
        """Premium formulas instructions contain key domain content."""
        skill = Skill.from_file(_SKILLS_DIR / "premium-formulas")
        assert "Risk Multiplier" in skill.instructions
        assert "Coverage Factor" in skill.instructions
        assert "no_claims_bonus" in skill.instructions

    def test_claims_workflow_allowed_tools(self) -> None:
        """Claims workflow declares get_claim_details as allowed tool."""
        skill = Skill.from_file(_SKILLS_DIR / "claims-workflow")
        assert "get_claim_details" in (skill.allowed_tools or [])

    def test_premium_formulas_allowed_tools(self) -> None:
        """Premium formulas declares get_product_info as allowed tool."""
        skill = Skill.from_file(_SKILLS_DIR / "premium-formulas")
        assert "get_product_info" in (skill.allowed_tools or [])


class TestSkillFromContent:
    """Verify Skill.from_content() works for future Registry integration."""

    def test_from_content_creates_skill(self) -> None:
        """Skill.from_content() parses inline SKILL.md content correctly."""
        content = """---
name: test-skill
description: A test skill for validation.
---
# Test Instructions

Follow these steps to complete the task.
"""
        skill = Skill.from_content(content)
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for validation."
        assert "Follow these steps" in skill.instructions

    def test_from_content_with_allowed_tools(self) -> None:
        """Skill.from_content() parses allowed-tools field."""
        content = """---
name: registry-skill
description: Skill loaded from Registry.
allowed-tools: get_data fetch_info
---
Use get_data and fetch_info to answer questions.
"""
        skill = Skill.from_content(content)
        assert skill.name == "registry-skill"
        assert "get_data" in (skill.allowed_tools or [])
        assert "fetch_info" in (skill.allowed_tools or [])


class TestAgentSkillsPlugin:
    """Verify AgentSkills plugin accepts Registry-loaded skills."""

    def test_plugin_accepts_programmatic_skills(self) -> None:
        """Plugin accepts Skill instances directly (Registry integration path)."""
        skill = Skill(
            name="inline-skill",
            description="Created programmatically.",
            instructions="Do the thing.",
        )
        plugin = AgentSkills(skills=[skill])
        skills = plugin.get_available_skills()
        assert len(skills) == 1
        assert skills[0].name == "inline-skill"


class TestSystemPrompt:
    """Verify base prompt references the skills tool correctly."""

    def test_prompt_references_skills_tool(self) -> None:
        """Base prompt mentions the skills tool."""
        prompt = (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        assert "skills" in prompt.lower()

    def test_prompt_does_not_reference_old_tools(self) -> None:
        """Base prompt does not reference deprecated load_* tools."""
        prompt = (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        assert "load_claims_workflow_context" not in prompt
        assert "load_premium_formulas_context" not in prompt

    def test_prompt_references_available_skills_block(self) -> None:
        """Base prompt instructs agent to check <available_skills>."""
        prompt = (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        assert "available_skills" in prompt
