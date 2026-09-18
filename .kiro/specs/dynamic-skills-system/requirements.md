# Requirements Document

## Introduction

The Dynamic Skills System governs the lifecycle of shared domain knowledge used by the Sage AI Assistant. Domain experts author portable `SKILL.md` files, the deployment process validates and publishes accepted files as approved AgentCore Registry `AGENT_SKILLS` records, and each agent process loads the approved records once at startup. The Strands `AgentSkills` plugin then provides progressive disclosure by placing Skill descriptors in the initial agent context and loading complete Skill bodies only when needed.

This specification covers the Skills lifecycle only. The customer discovery transcript from 21 August describes specialized capabilities for product creation, reports, workflows, and document templates while keeping business-data access behind separate services. That evidence supports reusable domain Skills and a strict separation between knowledge and data access. The identity and authorization discussions in the 21 August and 28 August transcripts belong to separate feature specifications and do not define requirements here.

## POC/MVP Completion Boundary

The current milestone is a proof of concept, not a production-hardening release. For this POC, the Dynamic Skills System is considered implemented when the repository can author Skills as `skills/<skill-name>/SKILL.md`, publish them as approved AgentCore Registry `AGENT_SKILLS` records, load the approved records once when the agent process starts, initialize one Strands `AgentSkills` plugin, and use the built-in local `skills` tool for progressive disclosure. The existing module-level `_fetch_skills_from_registry()` call and `_skills` collection provide the effective startup load and process-lifetime snapshot for this milestone; a separate `StartupSkillSnapshot` class or dedicated loader module is not required.

The POC implementation is complete in the repository, with the migration test suite passing. One live Registry-to-agent smoke test remains operational sign-off for a deployed demo; it is verification of the existing path, not an additional POC architecture requirement.

The stricter validation, boundary-rule, publication-planner, atomic-output, immutable-snapshot, exhaustive lifecycle-test, and integration-test requirements below are intentionally recorded as deferred production hardening. They do not block declaring the current POC complete.

## Scope Boundary

### In Scope

- Local `skills/<skill-name>/SKILL.md` authoring and deterministic validation.
- AgentCore Registry creation or reuse for Skill records.
- Idempotent `AGENT_SKILLS` record publication, update, submission, and approval.
- Startup-time retrieval of approved Registry records.
- Conversion of accepted Registry content through `Skill.from_content()`.
- One process-scoped `AgentSkills` plugin and process-lifetime Skill caching.
- Restart-only visibility of newly approved or updated Registry records.
- Progressive disclosure through Skill descriptors and the local built-in Skills Tool.
- Separation of shared domain knowledge from tenant data, credentials, and authorization logic.
- Automated verification of the preceding behavior.

### Out of Scope

Browser authentication, Cognito, AgentCore Identity, token exchange, JWT passthrough, Gateway authorization, MCP authorization, API authorization, public MCP access, product-core generation or writes, memory, observability, audit, cost attribution, analytics, non-Skill infrastructure deployment, and tenant-data retrieval are owned by separate feature specifications.

## Glossary

- **Dynamic_Skills_System**: The Skills-only capability governed by this specification, from local Skill authoring through process-scoped progressive disclosure.
- **Skill**: A Strands Skill containing reusable Shared_Domain_Knowledge and optional approved Data Tool names.
- **Candidate_SKILL_File**: A discovered SKILL File that has not yet passed every applicable validation condition.
- **Shared_Domain_Knowledge**: Tenant-independent workflows, formulas, rules, and instructions that apply across authorized business contexts.
- **Tenant_Data**: A business record or value belonging to a specific tenant, user, workspace, environment, policy, claim, product instance, or other protected data boundary.
- **Tenant_Specific_Identifier**: An identifier that selects or identifies a specific tenant or tenant-owned business record.
- **Authorization_Logic**: Logic that authenticates an identity, derives an authorization context, evaluates permissions, selects a protected data boundary, or grants or denies access.
- **Data_Tool**: A separately specified tool that retrieves or changes business data outside the Dynamic Skills System.
- **SKILL_File**: A UTF-8 Markdown file at `skills/<skill-name>/SKILL.md` containing YAML frontmatter and a non-empty Markdown body.
- **Skill_Authoring_Source**: The local `skills/` directory containing SKILL Files before Registry publication.
- **Skill_Validator**: The deterministic component that validates SKILL File encoding, structure, metadata, tool declarations, and content boundaries.
- **Applicable_Validation_Failure**: A failed validation condition that the Skill Validator can determine from the Candidate SKILL File without assuming that an earlier failed parse or decode operation succeeded.
- **Boundary_Rule_Set**: The version-controlled deterministic field constraints and prohibited-content markers used by the Skill Validator to detect tenant records or identifiers, credential material, and authorization logic in Candidate SKILL Files.
- **Skill_Name**: The canonical hyphenated identifier declared by a SKILL File and used as the corresponding Registry record name.
- **Allowed_Tools**: An optional list containing only approved Data Tool names that a Skill may use.
- **Skill_Descriptor**: The Skill name and description made available to the agent before activation.
- **Skill_Body**: The complete Markdown instructions following a SKILL File's frontmatter.
- **AgentCore_Registry**: The centrally governed Registry containing deployed `AGENT_SKILLS` records.
- **Registry_Record**: One AgentCore Registry `AGENT_SKILLS` record containing the complete accepted SKILL File in `skillMd.inlineContent`.
- **Registry_Deploy_Process**: The operation that validates local SKILL Files, creates or reuses the Registry, publishes changed Registry Records, submits changed records for approval, waits for approval, and writes non-secret identifiers.
- **Registry_Deployment_Output**: The generated manifest containing the Registry identifier and published Skill record identifiers and statuses.
- **Previous_Valid_Deployment_Output**: The most recent Registry Deployment Output written after every discovered SKILL File reached an approved Registry Record.
- **Startup_Skill_Loader**: The initialization operation that lists approved Registry Records, retrieves complete inline content, and converts accepted content to Strands Skill instances.
- **Startup_Skill_Snapshot**: The immutable set of Skill instances produced by one successful startup load operation, including an empty set when the Registry contains no approved Skill records.
- **Agent_Process**: One running Sage agent process with one Startup Skill Snapshot.
- **AgentSkills_Plugin**: The process-scoped Strands plugin initialized from the Startup Skill Snapshot.
- **Skills_Tool**: The built-in local Strands tool that returns a complete Skill Body for a recognized Skill name.
- **Skill_Activation**: A local Skills Tool operation that resolves a Skill Name against the Startup Skill Snapshot.
- **Test_Suite**: The automated property-based, unit, and integration tests for the Dynamic Skills System.

## Requirements

### Requirement 1: Skill Authoring and Validation

**User Story:** As a domain expert, I want portable and deterministically validated Skill files, so that shared domain knowledge can be changed independently of agent orchestration code.

#### Acceptance Criteria

1. THE Skill_Authoring_Source SHALL store each Skill at `skills/<skill-name>/SKILL.md`.
2. WHEN the Skill_Validator reads a Candidate_SKILL_File, THE Skill_Validator SHALL decode the complete file by using strict UTF-8 decoding without replacement characters.
3. IF strict UTF-8 decoding fails, THEN THE Skill_Validator SHALL reject the Candidate_SKILL_File and report the encoding failure.
4. WHEN the Skill_Validator parses a decoded Candidate_SKILL_File, THE Skill_Validator SHALL recognize exactly one YAML frontmatter block at the beginning of the file bounded by opening and closing `---` delimiters.
5. WHEN the Skill_Validator parses YAML frontmatter, THE Skill_Validator SHALL require a mapping and report every duplicate metadata key as a validation failure.
6. WHEN the Skill_Validator evaluates required metadata, THE Skill_Validator SHALL require `name` and `description` values that are non-empty strings after surrounding whitespace is removed.
7. WHEN the Skill_Validator evaluates a Skill_Name, THE Skill_Validator SHALL accept the Skill_Name only when the value matches `^[a-z0-9]+(?:-[a-z0-9]+)*$` and equals the parent directory name.
8. WHEN the Skill_Validator evaluates a Skill_Body, THE Skill_Validator SHALL accept the Skill_Body only when non-whitespace Markdown content follows the closing frontmatter delimiter.
9. WHERE a Candidate_SKILL_File declares Allowed_Tools, THE Skill_Validator SHALL accept the declaration only when every value names an approved Data_Tool.
10. WHEN the Skill_Validator accepts a SKILL_File, THE Skill_Validator SHALL preserve the complete decoded UTF-8 file content without frontmatter reconstruction or content normalization for Registry publication.
11. WHEN the Skill_Validator evaluates a Candidate_SKILL_File, THE Skill_Validator SHALL collect every Applicable_Validation_Failure before the Registry_Deploy_Process mutates a Registry_Record.
12. IF the Skill_Validator reports one or more Applicable_Validation_Failures, THEN THE Registry_Deploy_Process SHALL reject the Candidate_SKILL_File and return the source path with every reported failed condition.

### Requirement 2: Registry Publication and Approval

**User Story:** As a platform operator, I want accepted Skills published as approved Registry records, so that deployed agent processes use centrally governed knowledge.

#### Acceptance Criteria

1. WHEN the configured Registry identifier resolves to an AgentCore_Registry, THE Registry_Deploy_Process SHALL reuse that AgentCore_Registry.
2. IF no reusable AgentCore_Registry exists, THEN THE Registry_Deploy_Process SHALL create one AgentCore_Registry for the Dynamic_Skills_System.
3. WHEN the Registry_Deploy_Process evaluates existing Registry Records, THE Registry_Deploy_Process SHALL identify Registry Records by Skill_Name across the complete `AGENT_SKILLS` record listing.
4. IF more than one existing Registry_Record has the same Skill_Name, THEN THE Registry_Deploy_Process SHALL report a duplicate logical record failure before any Registry_Record mutation.
5. WHEN no Registry_Record exists for an accepted Skill_Name, THE Registry_Deploy_Process SHALL create one Registry_Record containing the complete accepted SKILL_File.
6. WHEN one Registry_Record exists for an accepted Skill_Name and the accepted SKILL_File differs from the published record content or metadata, THE Registry_Deploy_Process SHALL update that Registry_Record rather than create another logical record.
7. WHEN the Registry_Deploy_Process creates or updates a Registry_Record, THE Registry_Deploy_Process SHALL submit the changed Registry_Record for approval when the record becomes submittable.
8. WHEN one Registry_Record exists for an accepted Skill_Name with equivalent content and metadata and `APPROVED` status, THE Registry_Deploy_Process SHALL reuse the Registry_Record without mutation or approval submission.
9. WHEN the Registry_Deploy_Process evaluates a Skill publication result, THE Registry_Deploy_Process SHALL classify the Skill publication as successful only when the Registry_Record has `APPROVED` status.
10. IF a changed Registry_Record does not reach `APPROVED` status under the configured approval wait policy, THEN THE Registry_Deploy_Process SHALL report the Skill publication as unsuccessful.
11. WHEN every discovered SKILL_File has one approved Registry_Record, THE Registry_Deploy_Process SHALL atomically write a Registry_Deployment_Output containing the Registry identifier and each Skill_Name, record identifier, record reference, and final status.
12. IF any discovered SKILL_File fails validation, publication, submission, or approval, THEN THE Registry_Deploy_Process SHALL preserve the Previous_Valid_Deployment_Output without replacement.
13. THE Registry_Deployment_Output SHALL exclude SKILL_File content, Skill_Bodies, Tenant_Data, credentials, tokens, secret values, and authorization configuration.
14. WHEN the Registry_Deploy_Process runs again with unchanged accepted SKILL_Files and approved Registry Records, THE Registry_Deploy_Process SHALL reuse the same logical AgentCore_Registry and Registry Records.

### Requirement 3: Startup-Time Approved Skill Loading

**User Story:** As a platform operator, I want each agent process to load approved Registry Skills before serving requests, so that runtime knowledge reflects governed content.

#### Acceptance Criteria

1. WHEN an Agent_Process starts, THE Startup_Skill_Loader SHALL perform exactly one startup load operation before the Agent_Process accepts invocations.
2. WHEN the startup load operation begins, THE Startup_Skill_Loader SHALL list Registry Records whose descriptor type is `AGENT_SKILLS` and whose status is `APPROVED` from the configured AgentCore_Registry.
3. WHEN an approved-record listing contains multiple pages, THE Startup_Skill_Loader SHALL retrieve every page before completing the Startup_Skill_Snapshot.
4. WHEN the complete approved-record listing is empty, THE Startup_Skill_Loader SHALL create an empty Startup_Skill_Snapshot.
5. WHEN the Startup_Skill_Loader receives an approved Registry_Record, THE Startup_Skill_Loader SHALL retrieve the complete `skillMd.inlineContent` value.
6. WHEN retrieved inline content satisfies the Skill_Validator conditions, THE Startup_Skill_Loader SHALL create one Strands Skill through `Skill.from_content()`.
7. IF the configured Registry identifier is absent or does not resolve to the configured AgentCore_Registry, THEN THE Startup_Skill_Loader SHALL stop Agent_Process startup with a descriptive configuration error.
8. IF any page of the approved-record listing fails, THEN THE Startup_Skill_Loader SHALL stop Agent_Process startup without substituting local or previously cached Skill content.
9. IF an individual approved Registry_Record cannot be retrieved, lacks inline content, fails Skill validation, or cannot be converted to a Skill, THEN THE Startup_Skill_Loader SHALL exclude the Registry_Record and write a non-secret warning containing the record identifier and failure category without Registry content.
10. IF two or more successfully validated Registry Records resolve to the same Skill_Name, THEN THE Startup_Skill_Loader SHALL stop Agent_Process startup with a duplicate Skill Name error before initializing the AgentSkills_Plugin.
11. WHEN the startup load operation completes without a startup-stopping failure, THE Dynamic_Skills_System SHALL create one Startup_Skill_Snapshot and initialize exactly one AgentSkills_Plugin from that snapshot before accepting invocations.

### Requirement 4: Process-Lifetime Caching and Restart Visibility

**User Story:** As a platform operator, I want a stable Skill snapshot for each process, so that invocations avoid Registry latency and knowledge changes have a predictable activation boundary.

#### Acceptance Criteria

1. WHILE an Agent_Process is running, THE Dynamic_Skills_System SHALL use the same Startup_Skill_Snapshot for every invocation.
2. WHILE an Agent_Process is running, THE Startup_Skill_Loader SHALL perform no Registry reads for an invocation or Skill_Activation.
3. WHEN a Registry_Record is added, changed, or loses `APPROVED` status after the Startup_Skill_Snapshot is created, THE Agent_Process SHALL keep the existing Startup_Skill_Snapshot unchanged.
4. WHEN a new Agent_Process starts, THE Startup_Skill_Loader SHALL create a new Startup_Skill_Snapshot from the approved Registry Records visible to that startup load operation.
5. WHEN the Startup_Skill_Loader creates a new Startup_Skill_Snapshot, THE Dynamic_Skills_System SHALL assign that snapshot only to the starting Agent_Process.
6. WHEN the same Skill_Name is activated multiple times within one Agent_Process, THE Skills_Tool SHALL return the same complete Skill_Body from that Agent_Process's Startup_Skill_Snapshot.
7. THE Dynamic_Skills_System SHALL describe runtime Skill retention as process-lifetime caching with restart visibility.

### Requirement 5: Strands Progressive Disclosure

**User Story:** As a Sage user, I want the agent to load only relevant domain instructions, so that the initial context remains compact while complete governed instructions remain available on demand.

#### Acceptance Criteria

1. WHEN the AgentSkills_Plugin initializes, THE AgentSkills_Plugin SHALL expose exactly one Skill_Descriptor for each Skill in the Startup_Skill_Snapshot.
2. WHEN the AgentSkills_Plugin exposes a Skill_Descriptor, THE Skill_Descriptor SHALL contain the Skill_Name and description.
3. THE AgentSkills_Plugin SHALL exclude Skill_Bodies from the initial agent context.
4. WHEN a user request requires an available Skill, THE Dynamic_Skills_System SHALL perform Skill_Activation through the Skills_Tool before applying the Skill instructions.
5. WHEN the Skills_Tool receives a recognized Skill_Name, THE Skills_Tool SHALL return the complete Skill_Body from the Startup_Skill_Snapshot.
6. IF the Skills_Tool receives an unrecognized Skill_Name, THEN THE Skills_Tool SHALL return a descriptive not-found result without changing the Startup_Skill_Snapshot.
7. IF Skill_Activation fails for a recognized Skill_Name, THEN THE Skills_Tool SHALL leave the Startup_Skill_Snapshot unchanged.
8. WHEN the AgentSkills_Plugin performs Skill discovery, THE AgentSkills_Plugin SHALL invoke neither the AgentCore_Registry nor a Data_Tool.
9. WHEN the Skills_Tool performs Skill_Activation, THE Skills_Tool SHALL invoke neither the AgentCore_Registry nor a Data_Tool.

### Requirement 6: Shared-Knowledge Boundary

**User Story:** As a data and security owner, I want Skills limited to shared domain knowledge, so that Skill reuse cannot become a tenant-data or authorization channel.

#### Acceptance Criteria

1. THE Skill_Validator SHALL apply the same version-controlled Boundary_Rule_Set to every Candidate_SKILL_File before Registry publication.
2. WHEN a Candidate_SKILL_File matches a Boundary_Rule_Set condition for Tenant_Data, a Tenant_Specific_Identifier, credential material, or Authorization_Logic, THE Skill_Validator SHALL report each matched condition as an Applicable_Validation_Failure.
3. IF a Candidate_SKILL_File has a boundary-related Applicable_Validation_Failure, THEN THE Registry_Deploy_Process SHALL reject the Candidate_SKILL_File before creating or updating a Registry_Record.
4. WHERE a Candidate_SKILL_File declares Allowed_Tools, THE Skill_Validator SHALL accept only a list of approved Data_Tool names in the Allowed_Tools declaration.
5. WHEN the Skill_Validator accepts a Candidate_SKILL_File, THE Skill_Validator SHALL record that the Candidate_SKILL_File matched no Boundary_Rule_Set condition.
6. WHEN a user request depends on Tenant_Data, THE Dynamic_Skills_System SHALL derive no Tenant_Data solely from a Skill_Descriptor or Skill_Body.
7. WHEN a user request depends on an authorization decision, THE Dynamic_Skills_System SHALL derive no authorization result solely from a Skill_Descriptor or Skill_Body.
8. IF a Candidate_SKILL_File for an existing approved Skill_Name fails a Boundary_Rule_Set condition, THEN THE Registry_Deploy_Process SHALL preserve the existing approved Registry_Record content and the Previous_Valid_Deployment_Output.

### Requirement 7: Skills Lifecycle Verification

**User Story:** As an engineer, I want automated verification of the Skills lifecycle, so that publication, startup, caching, disclosure, and content boundaries remain correct as the system changes.

#### Acceptance Criteria

1. WHEN Skill validation property tests run, THE Test_Suite SHALL verify strict UTF-8 decoding, deterministic frontmatter and YAML parsing, duplicate metadata key rejection, canonical parent-matching Skill Names, required metadata, non-empty Skill Bodies, approved Allowed Tools, complete accepted-content preservation, complete Applicable Validation Failure reporting, and zero Registry mutation after rejection.
2. WHEN Registry publication tests run, THE Test_Suite SHALL verify Registry creation, Registry reuse, new-record creation, changed-record update, unchanged-approved reuse, duplicate logical record failure, and repeated-publication idempotency by Skill_Name.
3. WHEN Registry approval tests run, THE Test_Suite SHALL verify changed-record submission, successful publication only for `APPROVED` records, unsuccessful approval outcomes, atomic output replacement after complete success, and Previous Valid Deployment Output preservation after partial failure.
4. WHEN Startup Skill Loader listing tests run, THE Test_Suite SHALL verify approved-only `AGENT_SKILLS` filtering, complete pagination, an empty approved Registry, absent or unresolved Registry configuration failure, and failure of any listing page.
5. WHEN Startup Skill Loader record tests run, THE Test_Suite SHALL verify inline-content retrieval, Skill validation, `Skill.from_content()` conversion, record-level exclusion warnings, non-secret warning content, and startup failure for duplicate valid Skill Names.
6. WHEN process-lifetime caching tests run, THE Test_Suite SHALL verify one startup load per Agent_Process, zero invocation-time Registry reads, stable repeated activation, unchanged running-process snapshots after record addition, change, or loss of approval, and change visibility only through each new Agent_Process's own snapshot.
7. WHEN progressive-disclosure tests run, THE Test_Suite SHALL verify exactly one descriptor per snapshot Skill, initial context without Skill Bodies, complete cached bodies for recognized activation, unchanged snapshots after unknown or failed activation, and zero Registry or Data Tool invocations during discovery and activation.
8. WHEN shared-knowledge boundary tests run, THE Test_Suite SHALL verify deterministic Boundary Rule Set application, rejection of configured Tenant Data, Tenant Specific Identifier, credential, and Authorization Logic fixtures, approved Allowed Tools declarations, no tenant-data or authorization derivation solely from Skill content, and preservation of prior approved content and deployment output after boundary rejection.

## Correctness Properties

### Property 1: Skill Validation Determinism and Preservation

For every candidate Skill path and byte sequence, validation produces the same result and Applicable Validation Failures for the same approved Data Tool set and Boundary Rule Set. Validation succeeds only when strict UTF-8 decoding, deterministic frontmatter and YAML parsing, unique required metadata keys, canonical parent-matching Skill Name, approved Allowed Tools, and a non-empty Skill Body succeed. Every accepted source preserves its complete decoded content, and every rejected source causes no Registry Record mutation.

**Validates:** Requirements 1.1–1.12 and 7.1.

### Property 2: Registry Publication Convergence

For every accepted set of SKILL_Files and existing Registry state without duplicate logical records, publication creates missing records, updates changed records, reuses unchanged approved records, and converges on one logical AgentCore Registry and one logical Registry Record per Skill_Name. A publication is successful only for approved records, complete success atomically replaces the deployment output, and partial failure preserves the Previous Valid Deployment Output.

**Validates:** Requirements 2.1–2.14, 7.2, and 7.3.

### Property 3: Startup Snapshot Correctness

For every paginated approved Registry listing, the Startup_Skill_Snapshot contains exactly the uniquely named approved records that provide valid inline content and can be converted through `Skill.from_content()`. An empty listing produces an empty snapshot; a configuration, listing, or duplicate valid Skill Name failure prevents startup; and an invalid individual record is excluded with a non-secret categorized warning.

**Validates:** Requirements 3.1–3.11, 7.4, and 7.5.

### Property 4: Process Snapshot Stability

For every Agent_Process, invocation sequence, repeated activation sequence, and post-start Registry addition, change, or loss of approval, the process performs no invocation-time Registry read and keeps its Startup_Skill_Snapshot unchanged. Repeated activation returns the same complete body, and Registry state becomes observable only through the independently created snapshot of a new Agent_Process.

**Validates:** Requirements 4.1–4.7 and 7.6.

### Property 5: Progressive Disclosure and Knowledge Separation

For every accepted Startup_Skill_Snapshot, initial agent context contains exactly one descriptor per Skill without Skill Bodies, recognized activation returns the corresponding complete cached body, unknown or failed activation leaves the snapshot unchanged, and discovery and activation invoke neither the Registry nor Data Tools. Every Candidate SKILL File is evaluated by the deterministic Boundary Rule Set; a boundary rejection supplies no tenant data or authorization result from Skill content and preserves prior approved content and deployment output.

**Validates:** Requirements 5.1–5.9, 6.1–6.8, 7.7, and 7.8.
