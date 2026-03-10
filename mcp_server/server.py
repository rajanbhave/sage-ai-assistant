"""FastMCP entry point for the Sage AI Assistant MCP server.

Creates the ``FastMCP`` instance and registers all tools (context tools
and data tools). Run directly to start the MCP server:

    uv run python mcp_server/server.py

The server exposes all registered tools to the AgentCore Gateway for
semantic routing.

# Local verification:
#   Start MCP server:  uv run python mcp_server/server.py
#   Start agent:       uv run python agent/agent.py
#   Ask "What's the claims filing process?"
#     → agent should invoke load_claims_workflow_context
#   Ask "How is premium calculated?"
#     → agent should invoke load_premium_formulas_context
"""

from fastmcp import FastMCP
from mcp_server.tools.context_tools import register_context_tools
from mcp_server.tools.data_tools import register_data_tools

mcp = FastMCP("sage-mcp-server")

# Register context tools (load_claims_workflow_context, load_premium_formulas_context)
register_context_tools(mcp)

# Register data tools (get_product_info, get_claim_details)
register_data_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, stateless_http=True)
