"""Context tools for the Sage MCP server.

These tools load domain knowledge from Markdown skill files in the
``skills/`` directory at the project root. They are stateless readers —
no caching — so updates to skill files take effect on the next invocation
without redeployment.

Tool descriptions are crafted for AgentCore Gateway semantic routing
accuracy (Requirement 8).
"""

from pathlib import Path
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

# Project root is two levels up from this file (mcp_server/tools/context_tools.py)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SKILLS_DIR = _PROJECT_ROOT / "skills"


def register_context_tools(mcp: FastMCP) -> None:
    """Register all context tools onto the given FastMCP instance.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool(
        description=(
            "Load claims processing workflow context. Use when the user asks about "
            "claim status, claim filing procedures, claim approval workflows, claim "
            "documentation requirements, or any claims-related processes."
        )
    )
    def load_claims_workflow_context() -> str:
        """Load and return the claims processing domain knowledge.

        Reads ``skills/claims_workflow.md`` from the project root and returns
        its full Markdown content as a string. The content covers claim filing
        procedures, status tracking, approval workflows, documentation
        requirements, and SLAs.

        Returns:
            The full Markdown content of the claims workflow skill file.

        Raises:
            ToolError: If the skill file is missing or cannot be read.
        """
        skill_path = _SKILLS_DIR / "claims_workflow.md"
        return _read_skill_file(skill_path)

    @mcp.tool(
        description=(
            "Load premium calculation formulas and rules. Use when the user asks about "
            "premium calculations, pricing factors, discount rules, rate tables, "
            "or how insurance premiums are determined for any product type."
        )
    )
    def load_premium_formulas_context() -> str:
        """Load and return the premium calculation formulas and rules.

        Reads ``skills/premium_formulas.md`` from the project root and returns
        its full Markdown content as a string. The content covers base premium
        methodology, pricing factors, discount rules, rate tables, and
        product-type-specific calculation rules.

        Returns:
            The full Markdown content of the premium formulas skill file.

        Raises:
            ToolError: If the skill file is missing or cannot be read.
        """
        skill_path = _SKILLS_DIR / "premium_formulas.md"
        return _read_skill_file(skill_path)


def _read_skill_file(skill_path: Path) -> str:
    """Read a skill Markdown file and return its content.

    Args:
        skill_path: Absolute path to the skill file.

    Returns:
        The file content as a string.

    Raises:
        ToolError: With error_type ``"missing_skill"`` if the file does not
            exist or cannot be read due to a permission error.
    """
    try:
        display = skill_path.relative_to(_PROJECT_ROOT)
    except ValueError:
        display = skill_path

    try:
        return skill_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ToolError(f"Skill file not found: {display}")
    except PermissionError:
        raise ToolError(f"Cannot read skill file: {display}")
