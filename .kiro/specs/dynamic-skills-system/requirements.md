# Requirements Document

## Introduction

The Dynamic Skills System replaces the current hardcoded `load_*` MCP context tools in the Sage AI Assistant with the Strands SDK `AgentSkills` plugin — a built-in progressive disclosure system that follows the [Agent Skills specification](https://agentskills.io/specification). Instead of one MCP tool per skill file, the plugin automatically injects lightweight skill descriptors into the system prompt and exposes a `skills` tool that the agent calls on-demand to retrieve full skill instructions.

Skills are stored in the AWS AgentCore Registry as `AGENT_SKILLS` records and fetched at agent startup via the Registry API. The agent creates `Skill` instances from the Registry content using `Skill.from_content()` and passes them to the `AgentSkills` plugin. Local `skills/` directories serve as the authoring source — a deploy script publishes them to the Registry.

A deploy script (`scripts/deploy_registry.py`) creates the Registry with IAM auth and auto-approval, reads each local `SKILL.md` file, and publishes it as an `AGENT_SKILLS` record. The agent reads from the Registry at startup (once per process), not from local files.

## Glossary

- **AgentSkills_Plugin**: The Strands SDK `AgentSkills` class (`strands.AgentSkills`) that extends the `Plugin` base class to provide skill discovery, system prompt injection, and on-demand loading via a built-in `skills` tool.
- **Skill**: A Strands SDK dataclass (`strands.Skill`) representing a skill with `name`, `description`, `instructions`, and optional metadata. Can be loaded from filesystem (`Skill.from_file`), parsed from content (`Skill.from_content`), or created programmatically.
- **Skill_Descriptor**: The lightweight metadata (name + description) that the `AgentSkills` plugin automatically injects into the system prompt as an `<available_skills>` XML block. ~50–80 tokens per skill.
- **Skill_Body**: The full Markdown instructions from a SKILL.md file (~2–5k tokens). Loaded on-demand when the agent calls the `skills` tool.
- **SKILL_File**: A Markdown file named `SKILL.md` with YAML frontmatter (delimited by `---`) containing skill metadata (name, description, optional allowed-tools) followed by the skill's full instructions. Located in a per-skill directory (e.g., `skills/claims-workflow/SKILL.md`).
- **Skills_Tool**: The built-in `skills` tool automatically registered by the `AgentSkills` plugin. The agent calls `skills(skill_name="claims-workflow")` to load full instructions on demand.
- **AgentCore_Registry**: The AWS AgentCore Registry service that stores skill records (`AGENT_SKILLS` type) with `skillMd.inlineContent` containing the full SKILL.md content. The agent fetches all approved `AGENT_SKILLS` records at startup via IAM-authenticated API calls.
- **Registry_Deploy_Script**: The `scripts/deploy_registry.py` script that creates the Registry (IAM auth, auto-approval) and publishes local `SKILL.md` files as `AGENT_SKILLS` records.
- **Strands_Agent**: The Strands SDK `Agent` instance configured in `agent/agent.py` that orchestrates tool use, model invocation, and streaming responses.

## Requirements

### Requirement 1: Skill File Format (Agent Skills Specification)

**User Story:** As a domain expert, I want to author skills as SKILL.md files following the Agent Skills specification, so that skills are portable across any agent framework that supports the spec.

#### Acceptance Criteria

1. WHEN a `SKILL.md` file with valid YAML frontmatter containing `name` and `description` fields is placed in a skill directory, THE `AgentSkills` plugin SHALL discover and register the skill.
2. WHEN a `SKILL.md` file contains YAML frontmatter missing the required `name` field, THE `AgentSkills` plugin SHALL skip the file and log a warning.
3. WHEN a `SKILL.md` file contains YAML frontmatter missing the required `description` field, THE `AgentSkills` plugin SHALL skip the file and log a warning.
4. THE SKILL_File format SHALL support an optional `allowed-tools` field listing tool names the skill uses.
5. THE SKILL_File body (below the closing `---` delimiter) SHALL contain the full Markdown instructions for the skill.
6. EACH skill SHALL reside in its own directory named to match the skill name (e.g., `skills/claims-workflow/SKILL.md`).

### Requirement 2: Progressive Disclosure via AgentSkills Plugin

**User Story:** As an AI agent, I need lightweight skill descriptors in my system prompt at startup, so that I can identify which skills are relevant to a user's query and decide which to load — without bloating the context window.

#### Acceptance Criteria

1. WHEN the Strands_Agent is initialized with the `AgentSkills` plugin, THE plugin SHALL automatically inject an `<available_skills>` XML block into the system prompt containing all skill names and descriptions.
2. THE plugin SHALL refresh the `<available_skills>` block before each agent invocation, so that runtime changes to available skills take effect immediately.
3. THE plugin SHALL keep each skill's system prompt footprint to ~50–80 tokens (name + description only).
4. THE full skill instructions SHALL NOT be loaded into the system prompt at startup — only on-demand via the `skills` tool.

### Requirement 3: On-Demand Skill Loading

**User Story:** As an AI agent, I need a tool to load the full instructions of a skill on-demand, so that I only consume context window tokens for skills that are relevant to the current conversation.

#### Acceptance Criteria

1. WHEN the agent calls the `skills` tool with a valid skill name, THE tool SHALL return the full skill instructions and a listing of any resource files.
2. WHEN the agent calls the `skills` tool with a skill name that does not exist, THE tool SHALL return an error message.
3. THE `skills` tool SHALL be automatically registered by the `AgentSkills` plugin — no manual tool registration required.
4. WHEN the same skill is loaded multiple times within a single conversation, THE tool SHALL return the skill content each time without error.
5. THE plugin SHALL track activated skills in `agent.state` for session persistence.

### Requirement 4: Migration from Current Context Tools

**User Story:** As a platform operator, I want the existing claims workflow and premium formulas skills to work through the new skill system, so that the migration is seamless and no domain knowledge is lost.

#### Acceptance Criteria

1. WHEN the Dynamic Skills System is active, THE existing `skills/claims_workflow.md` and `skills/premium_formulas.md` files SHALL be restructured into per-skill directories with `SKILL.md` files containing appropriate YAML frontmatter.
2. WHEN a user asks a claims-related question, THE Strands_Agent SHALL load the claims workflow skill via the `skills` tool and provide an equivalent answer to the current `load_claims_workflow_context` tool behavior.
3. WHEN a user asks a premium calculation question, THE Strands_Agent SHALL load the premium formulas skill via the `skills` tool and provide an equivalent answer to the current `load_premium_formulas_context` tool behavior.
4. THE base system prompt (`agent/prompts/system.md`) SHALL be updated to reference the `skills` tool instead of the old `load_*` context tools.

### Requirement 5: AgentCore Runtime Integration

**User Story:** As a platform operator, I want the skill system to integrate cleanly with the existing BedrockAgentCoreApp and Strands Agent setup, so that the agent continues to work with MCP tools from the Gateway while also having access to skills.

#### Acceptance Criteria

1. WHEN the agent handles a request, THE Strands_Agent SHALL have access to both the `skills` tool (from the plugin) and MCP tools from the AgentCore Gateway.
2. THE `skills` tool SHALL be registered automatically by the plugin, separate from the MCP tools provided by the Gateway.
3. THE agent entrypoint (`agent/agent.py`) SHALL continue to support the existing request flow: JWT tenant extraction, MCP client creation, and streaming responses.
4. THE `AgentSkills` plugin SHALL be initialized once and reused across requests (not recreated per invocation).

### Requirement 6: Skill File Authoring Conventions

**User Story:** As a domain expert, I want clear conventions for authoring skill files, so that new skills are consistent and discoverable by the plugin.

#### Acceptance Criteria

1. THE SKILL_File format SHALL require YAML frontmatter delimited by `---` lines at the top of the file, containing at minimum `name` (string) and `description` (string) fields.
2. THE SKILL_File format SHALL support an optional `allowed-tools` field as a space-delimited list of tool names.
3. THE SKILL_File `name` field SHALL use lowercase hyphenated format (e.g., `claims-workflow`, `premium-formulas`) per the Agent Skills specification.
4. THE SKILL_File `description` field SHALL be a single sentence summarizing when the skill is relevant.
5. THE SKILL_File body SHALL be standard Markdown with no restrictions on content structure, headings, or length.
6. EACH skill directory MAY contain optional `scripts/`, `references/`, and `assets/` subdirectories for resource files.

### Requirement 7: AgentCore Registry Integration

**User Story:** As a platform operator, I want skills stored in the AgentCore Registry so that they are centrally governed, versioned, and discoverable — and the agent loads them from the Registry at startup.

#### Acceptance Criteria

1. A deploy script (`scripts/deploy_registry.py`) SHALL create an AgentCore Registry named `sage-skills` with IAM authorization and auto-approval enabled.
2. THE deploy script SHALL read each `SKILL.md` file from local `skills/*/SKILL.md` directories and publish it as an `AGENT_SKILLS` record in the Registry, with the full SKILL.md content stored in `agentSkills.skillMd.inlineContent`.
3. THE deploy script SHALL be idempotent — re-running it SHALL update existing records rather than fail on duplicates.
4. THE deploy script SHALL save the Registry ID and record ARNs to `scripts/registry_output.json` for use by the agent.
5. AT agent startup, THE agent SHALL fetch all approved `AGENT_SKILLS` records from the Registry using `list_registry_records` and `get_registry_record` API calls with IAM auth.
6. FOR each fetched record, THE agent SHALL create a `Skill` instance using `Skill.from_content()` with the `skillMd.inlineContent` value.
7. THE agent SHALL pass the fetched `Skill` instances to the `AgentSkills` plugin instead of pointing at local filesystem directories.
8. THE Registry ID SHALL be configured via the `SKILL_REGISTRY_ID` environment variable.
9. THE runtime behavior (progressive disclosure, on-demand loading, prompt injection) SHALL be identical to the local filesystem approach.
