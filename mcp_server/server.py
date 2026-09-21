"""FastMCP entry point for the Sage AI Assistant MCP server.

Creates the ``FastMCP`` instance and registers data tools. Run directly
to start the MCP server:

    uv run python mcp_server/server.py

The server exposes all registered tools to the AgentCore Gateway for
semantic routing. Context tools (load_*) have been replaced by the
Strands AgentSkills plugin in the agent layer.

# Local verification:
#   Start MCP server:  uv run python mcp_server/server.py
#   Start agent:       uv run python agent/agent.py
"""

from fastmcp import FastMCP
from mcp_server.tools.data_tools import register_data_tools

mcp = FastMCP("sage-mcp-server")

# Register data tools (get_product_info, get_claim_details)
register_data_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, stateless_http=True)
