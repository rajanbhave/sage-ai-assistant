#!/usr/bin/env python3
"""Deploy skills to the AgentCore Registry.

Steps:
  1. Create (or reuse) the ``sage-skills`` Registry with IAM auth and auto-approval
  2. Scan ``skills/*/SKILL.md`` for skill files
  3. Publish each skill as an ``AGENT_SKILLS`` record
  4. Wait for records to reach ``APPROVED`` status
  5. Save outputs to ``scripts/registry_output.json``

Prerequisites:
  - AWS credentials configured (aws configure)
  - Skill files authored in ``skills/<name>/SKILL.md``

Usage:
  uv run python scripts/deploy_registry.py

Environment variables (optional overrides):
  AWS_REGION      — defaults to us-east-1
  REGISTRY_NAME   — registry name (defaults to sage-skills)
"""

import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any

# Force IPv4 — macOS often resolves AWS endpoints to IPv6 but the route hangs.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args, **kwargs):
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else results


socket.getaddrinfo = _ipv4_getaddrinfo

import boto3

# ── Configuration ─────────────────────────────────────────────────────

REGION = os.environ.get("AWS_REGION", "us-east-1")
REGISTRY_NAME = os.environ.get("REGISTRY_NAME", "sage-skills")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
OUTPUT_FILE = SCRIPT_DIR / "registry_output.json"


def load_previous_output() -> dict:
    """Load previously saved registry output if it exists."""
    if OUTPUT_FILE.exists():
        try:
            return json.loads(OUTPUT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields from SKILL.md content.

    Args:
        content: Full SKILL.md file content.

    Returns:
        Dict with parsed frontmatter fields (name, description, etc.).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}

    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def discover_skills() -> list[dict]:
    """Scan skills/ directory for SKILL.md files.

    Returns:
        List of dicts with keys: name, description, content, path.
    """
    skills = []
    if not SKILLS_DIR.is_dir():
        print(f"WARNING: Skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)

        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", f"Skill: {name}")

        skills.append({
            "name": name,
            "description": description,
            "content": content,
            "path": str(skill_file.relative_to(PROJECT_ROOT)),
        })

    return skills


def step1_create_registry(client: Any, prev: dict) -> tuple[str, str]:
    """Create or reuse the sage-skills Registry.

    Args:
        client: boto3 bedrock-agentcore-control client.
        prev: Previously saved output dict.

    Returns:
        Tuple of (registry_arn, registry_id).
    """
    print("Step 1: Setting up AgentCore Registry...")

    # Check previous output
    saved_arn = prev.get("registryArn")
    saved_id = prev.get("registryId")
    if saved_arn and saved_id:
        try:
            client.get_registry(registryId=saved_id)
            print(f"  Reusing registry from registry_output.json: {saved_id}")
            return saved_arn, saved_id
        except client.exceptions.ResourceNotFoundException:
            print(f"  Previous registry {saved_id} not found, creating new one...")
        except Exception:
            pass

    # Try to find existing registry by listing
    try:
        resp = client.list_registries()
        for reg in resp.get("registries", []):
            if reg.get("name") == REGISTRY_NAME:
                arn = reg["registryArn"]
                rid = arn.rsplit("/", 1)[-1]
                print(f"  Found existing registry: {rid}")
                return arn, rid
    except Exception as e:
        print(f"  Note: Could not list registries: {e}")

    # Create new registry
    print(f"  Creating registry: {REGISTRY_NAME}")
    try:
        resp = client.create_registry(
            name=REGISTRY_NAME,
            description="Sage AI Assistant skill registry for insurance domain knowledge",
            authorizerType="AWS_IAM",
            approvalConfiguration={"autoApproval": True},
        )
        arn = resp["registryArn"]
        rid = arn.rsplit("/", 1)[-1]
        print(f"  Created registry: {rid}")
        print(f"  Registry ARN: {arn}")

        # Wait for registry to be ready
        print("  Waiting for registry to be ready...", end="", flush=True)
        for _ in range(30):
            time.sleep(2)
            print(".", end="", flush=True)
            try:
                reg = client.get_registry(registryId=rid)
                status = reg.get("status", "")
                if status in ("ACTIVE", "READY"):
                    break
            except Exception:
                pass
        print(" done.")

        return arn, rid
    except client.exceptions.ConflictException:
        # Registry name already taken — find it
        print(f"  Registry '{REGISTRY_NAME}' already exists, finding it...")
        resp = client.list_registries()
        for reg in resp.get("registries", []):
            if reg.get("name") == REGISTRY_NAME:
                arn = reg["registryArn"]
                rid = arn.rsplit("/", 1)[-1]
                print(f"  Found: {rid}")
                return arn, rid
        print("ERROR: Registry conflict but could not find it", file=sys.stderr)
        sys.exit(1)


def step2_publish_skills(
    client: Any, registry_id: str, skills: list[dict], prev: dict,
) -> list[dict]:
    """Publish each skill as an AGENT_SKILLS record.

    Args:
        client: boto3 bedrock-agentcore-control client.
        registry_id: The Registry ID to publish to.
        skills: List of skill dicts from discover_skills().
        prev: Previously saved output dict.

    Returns:
        List of dicts with keys: name, recordArn, recordId, status.
    """
    print(f"\nStep 2: Publishing {len(skills)} skill(s) to registry...")

    # Build lookup of existing records
    existing_records = {}
    try:
        resp = client.list_registry_records(
            registryId=registry_id,
            descriptorType="AGENT_SKILLS",
        )
        for rec in resp.get("registryRecords", []):
            existing_records[rec["name"]] = rec
    except Exception as e:
        print(f"  Note: Could not list existing records: {e}")

    results = []
    for skill in skills:
        name = skill["name"]
        description = skill["description"]
        content = skill["content"]

        print(f"\n  Publishing: {name}")
        print(f"    Source: {skill['path']}")
        print(f"    Description: {description}")

        existing = existing_records.get(name)
        if existing:
            record_id = existing["recordId"]
            record_arn = existing["recordArn"]
            status = existing.get("status", "")
            print(f"    Record exists (ID: {record_id}, status: {status}), updating...")

            try:
                # update_registry_record uses optionalValue wrappers
                client.update_registry_record(
                    registryId=registry_id,
                    recordId=record_id,
                    description={"optionalValue": description},
                    descriptors={
                        "optionalValue": {
                            "agentSkills": {
                                "optionalValue": {
                                    "skillMd": {
                                        "optionalValue": {
                                            "inlineContent": content,
                                        }
                                    },
                                }
                            }
                        }
                    },
                )
                print(f"    Updated record: {record_id}")
            except Exception as e:
                print(f"    Warning: Could not update record: {e}")

            results.append({
                "name": name,
                "recordArn": record_arn,
                "recordId": record_id,
                "status": status,
            })
        else:
            # Create new record
            try:
                resp = client.create_registry_record(
                    registryId=registry_id,
                    name=name,
                    description=description,
                    descriptorType="AGENT_SKILLS",
                    descriptors={
                        "agentSkills": {
                            "skillMd": {"inlineContent": content},
                        }
                    },
                )
                record_arn = resp["recordArn"]
                record_id = record_arn.rsplit("/", 1)[-1]
                status = resp.get("status", "CREATING")
                print(f"    Created record: {record_id} (status: {status})")

                results.append({
                    "name": name,
                    "recordArn": record_arn,
                    "recordId": record_id,
                    "status": status,
                })
            except client.exceptions.ConflictException:
                print(f"    Record '{name}' already exists (race condition), skipping...")
            except Exception as e:
                print(f"    ERROR: Failed to create record: {e}", file=sys.stderr)

    return results


def step3_wait_for_draft_and_submit(
    client: Any, registry_id: str, records: list[dict],
) -> None:
    """Wait for records to reach DRAFT, then submit for approval.

    Records transition: CREATING → DRAFT → (submit) → APPROVED (auto-approval).

    Args:
        client: boto3 bedrock-agentcore-control client.
        registry_id: The Registry ID.
        records: List of record dicts from step2.
    """
    print(f"\nStep 3: Waiting for records to be ready and submitting for approval...")

    # First, wait for any CREATING records to reach DRAFT
    creating = [r for r in records if r["status"] == "CREATING"]
    if creating:
        print("  Waiting for records to finish creating...", end="", flush=True)
        for attempt in range(60):
            time.sleep(2)
            all_ready = True
            for rec in creating:
                try:
                    resp = client.get_registry_record(
                        registryId=registry_id,
                        recordId=rec["recordId"],
                    )
                    status = resp.get("status", "")
                    rec["status"] = status
                    if status == "CREATING":
                        all_ready = False
                except Exception:
                    all_ready = False
            if all_ready:
                break
            print(".", end="", flush=True)
        print(" done.")

    # Submit DRAFT records for approval
    for rec in records:
        if rec["status"] in ("DRAFT", "UPDATING"):
            print(f"  Submitting {rec['name']} for approval...")
            try:
                resp = client.submit_registry_record_for_approval(
                    registryId=registry_id,
                    recordId=rec["recordId"],
                )
                rec["status"] = resp.get("status", rec["status"])
                print(f"    Status: {rec['status']}")
            except Exception as e:
                print(f"    Warning: Could not submit for approval: {e}")

    # Wait for PENDING_APPROVAL records to reach APPROVED
    pending = [r for r in records if r["status"] not in ("APPROVED",)]
    if pending:
        print("  Waiting for approval...", end="", flush=True)
        for attempt in range(60):
            time.sleep(2)
            all_done = True
            for rec in pending:
                try:
                    resp = client.get_registry_record(
                        registryId=registry_id,
                        recordId=rec["recordId"],
                    )
                    status = resp.get("status", "")
                    rec["status"] = status
                    if status not in ("APPROVED",):
                        all_done = False
                except Exception:
                    all_done = False
            if all_done:
                break
            print(".", end="", flush=True)
        print(" done.")

    print()
    for rec in records:
        print(f"  {rec['name']}: {rec['status']}")


def step4_save_outputs(
    registry_arn: str, registry_id: str, records: list[dict],
) -> None:
    """Save deployment outputs to registry_output.json.

    Args:
        registry_arn: The Registry ARN.
        registry_id: The Registry ID.
        records: List of record dicts.
    """
    print(f"\nStep 4: Saving deployment outputs...")

    output = {
        "registryArn": registry_arn,
        "registryId": registry_id,
        "registryName": REGISTRY_NAME,
        "region": REGION,
        "records": records,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2) + "\n")
    print(f"  Saved to: {OUTPUT_FILE}")


def main() -> None:
    """Run all deployment steps."""
    print("=== Deploying Skills to AgentCore Registry ===")
    print(f"Region: {REGION}")
    print(f"Registry name: {REGISTRY_NAME}")
    print(f"Skills directory: {SKILLS_DIR}\n")

    prev = load_previous_output()
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # Discover local skills
    skills = discover_skills()
    if not skills:
        print("WARNING: No SKILL.md files found in skills/*/", file=sys.stderr)
        print("  Create skill directories with SKILL.md files first.")
        sys.exit(0)

    print(f"Found {len(skills)} skill(s):")
    for s in skills:
        print(f"  - {s['name']} ({s['path']})")
    print()

    # Step 1: Create or reuse registry
    registry_arn, registry_id = step1_create_registry(client, prev)

    # Step 2: Publish skills
    records = step2_publish_skills(client, registry_id, skills, prev)

    # Step 3: Wait for draft, submit for approval, wait for approved
    step3_wait_for_draft_and_submit(client, registry_id, records)

    # Step 4: Save outputs
    step4_save_outputs(registry_arn, registry_id, records)

    print("\n=== Registry deployment complete ===\n")
    print(f"  Registry:  {registry_id} ({REGISTRY_NAME})")
    print(f"  Records:   {len(records)}")
    for rec in records:
        print(f"    - {rec['name']}: {rec['status']}")
    print(f"\nNext steps:")
    print(f"  1. Deploy the agent with SKILL_REGISTRY_ID:")
    print(f"     bash scripts/deploy_agent.sh")
    print(f"  2. Or set the env var for local testing:")
    print(f"     export SKILL_REGISTRY_ID={registry_id}")


if __name__ == "__main__":
    main()
