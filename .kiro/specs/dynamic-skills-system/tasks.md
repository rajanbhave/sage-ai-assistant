# Implementation Plan: Dynamic Skills System

## Overview

Replace the hardcoded `load_*` MCP context tools and the custom `SkillRegistry` with the Strands SDK `AgentSkills` plugin. Implementation proceeds: skill file migration → agent wiring → MCP cleanup → old code removal → testing.

## Tasks

- [x] 1. Migrate existing skill files to Agent Skills specification format
  - [x] 1.1 Create skill directory structure and SKILL.md files
    - Create `skills/claims-workflow/` directory
    - Create `skills/claims-workflow/SKILL.md` with YAML frontmatter (`name: claims-workflow`, `description`, `allowed-tools: get_claim_details`) and the existing claims workflow Markdown body from `skills/claims_workflow.md`
    - Create `skills/premium-formulas/` directory
    - Create `skills/premium-formulas/SKILL.md` with YAML frontmatter (`name: premium-formulas`, `description`, `allowed-tools: get_product_info`) and the existing premium formulas Markdown body from `skills/premium_formulas.md`
    - Verify all original Markdown content is preserved below the frontmatter
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 4.1, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 1.2 Remove old flat skill files
    - Delete `skills/claims_workflow.md`
    - Delete `skills/premium_formulas.md`
    - _Requirements: 4.1_

- [x] 2. Wire AgentSkills plugin into agent entrypoint
  - [x] 2.1 Update `agent/agent.py` to use `AgentSkills` plugin
    - Add `from strands import AgentSkills` import
    - Initialize `_skills_plugin = AgentSkills(skills=Path(__file__).parent.parent / "skills")` at module level
    - In `invoke()`, pass `plugins=[_skills_plugin]` to the `Agent` constructor
    - Keep existing `tools=tools` (MCP tools from Gateway) — the plugin auto-registers the `skills` tool separately
    - Preserve existing request flow: JWT tenant extraction, MCP client creation, streaming responses
    - _Requirements: 2.1, 2.2, 3.3, 5.1, 5.2, 5.3, 5.4_

  - [x] 2.2 Update base system prompt (`agent/prompts/system.md`)
    - Remove references to old `load_claims_workflow_context` and `load_premium_formulas_context` tools
    - Add instruction to check `<available_skills>` and call the `skills` tool before answering domain questions
    - Keep behavioral constraints (no hallucination, respond in English, be concise)
    - _Requirements: 4.4_

- [x] 3. Checkpoint — Verify agent works with new skill system
  - Start agent locally and verify skills are discovered
  - Test claims-related question triggers `skills(skill_name="claims-workflow")`
  - Test premium-related question triggers `skills(skill_name="premium-formulas")`
  - Ask the user if questions arise

- [x] 4. Clean up deprecated code
  - [x] 4.1 Remove context tools from MCP server
    - Delete `mcp_server/tools/context_tools.py`
    - Remove `register_context_tools` import and call from `mcp_server/server.py`
    - MCP server retains only data tools (`get_product_info`, `get_claim_details`)
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.2 Remove custom SkillRegistry
    - Delete `agent/skill_registry.py`
    - Delete `tests/test_skill_registry.py`
    - _Requirements: N/A — replaced by Strands plugin_

- [x] 5. Write migration verification tests
  - [x]* 5.1 Create `tests/test_skills_migration.py`
    - Test `skills/claims-workflow/SKILL.md` parses correctly via `Skill.from_file()` with expected name, description
    - Test `skills/premium-formulas/SKILL.md` parses correctly via `Skill.from_file()` with expected name, description
    - Test skill names follow hyphenated format (Req 6.3)
    - Test `Skill.from_content()` works with inline SKILL.md content (validates future Registry path, Req 7.1)
    - Test `AgentSkills` plugin initializes successfully with `skills/` directory
    - _Requirements: 4.1, 6.3, 7.1, 7.2_

  - [x]* 5.2 Verify base prompt references `skills` tool
    - Test `agent/prompts/system.md` contains reference to `skills` tool
    - Test `agent/prompts/system.md` does NOT contain references to old `load_*` tools
    - _Requirements: 4.4_

- [x] 6. Final checkpoint — Ensure all tests pass
  - Run `uv run pytest` and verify all tests pass
  - Ask the user if questions arise

- [x] 7. Create Registry deploy script
  - [x] 7.1 Create `scripts/deploy_registry.py`
    - Include IPv4 monkey-patch (same pattern as `deploy_gateway.py`)
    - Create `sage-skills` Registry with `authorizerType="AWS_IAM"` and `approvalConfiguration={"autoApproval": True}`
    - Handle `ConflictException` for existing registry — reuse it
    - Scan `skills/*/SKILL.md` directories for skill files
    - For each skill: read SKILL.md content, extract description from frontmatter, create `AGENT_SKILLS` record with `agentSkills.skillMd.inlineContent`
    - Handle `ConflictException` for existing records — update them
    - Wait for records to reach `APPROVED` status (poll with backoff)
    - Save Registry ID and record ARNs to `scripts/registry_output.json`
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 8. Update agent to fetch skills from Registry
  - [x] 8.1 Add `_fetch_skills_from_registry()` function to `agent/agent.py`
    - Read `SKILL_REGISTRY_ID` from environment variable
    - Call `list_registry_records(registryId, descriptorType="AGENT_SKILLS", status="APPROVED")`
    - For each record, call `get_registry_record()` to get full `skillMd.inlineContent`
    - Create `Skill.from_content()` for each record
    - Return list of `Skill` instances
    - Log number of skills fetched
    - _Requirements: 7.5, 7.6, 7.7, 7.8_

  - [x] 8.2 Update module-level initialization in `agent/agent.py`
    - Replace `AgentSkills(skills=_SKILLS_DIR)` with `AgentSkills(skills=_fetch_skills_from_registry(SKILL_REGISTRY_ID))`
    - Add `SKILL_REGISTRY_ID` to environment variable reads
    - _Requirements: 7.7, 7.8, 7.9_

  - [x] 8.3 Update `scripts/deploy_agent.sh` to pass `SKILL_REGISTRY_ID` env var
    - Read Registry ID from `scripts/registry_output.json`
    - Pass as environment variable to the agent runtime
    - _Requirements: 7.8_

- [x] 9. Checkpoint — Deploy and verify Registry integration
  - Run `uv run python scripts/deploy_registry.py` to create Registry and publish skills
  - Verify records are created and approved in the Registry
  - Test agent startup fetches skills from Registry
  - Run `uv run pytest` to verify all tests still pass
  - Ask the user if questions arise

## Notes

- Tasks 1–6 are complete (local skills + AgentSkills plugin)
- Tasks 7–9 add AgentCore Registry integration
- The deploy order is: Registry (`deploy_registry.py`) → MCP (`deploy_mcp.sh`) → Agent (`deploy_agent.sh`)
- The agent fetches skills from the Registry once at startup (module-level init), not per request
- `SKILL_REGISTRY_ID` environment variable controls which Registry the agent reads from
- The `skills/` directory remains as the authoring source — `deploy_registry.py` publishes to the Registry
- IAM auth is used for Registry API calls (reuses existing AWS credentials)
- Auto-approval is enabled so records go directly to `APPROVED` status
- The `deploy_registry.py` script follows the same patterns as `deploy_gateway.py` (IPv4 patch, output JSON, idempotent)
- `pyyaml` is needed by the deploy script to parse SKILL.md frontmatter for the record description
