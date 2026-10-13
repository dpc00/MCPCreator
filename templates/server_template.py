"""{name}: an MCP server made with MCP Creator.

Add it to Claude Code, with the full path of this file:
    claude mcp add {dashname} python "<full path of this file>"
Sublime Text: command palette, "MCP Creator: Copy Add Command" copies that line for you,
and "MCP Creator: Test Server" lists the tools this file serves.
Print only to stderr from a tool: stdout belongs to the protocol.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_creator import Tool, arg, opt, serve


class Hello(Tool):
    """Say hello to someone."""

    who = arg(str, "Who to greet")

    def call(self, who):
        return "Hello, %s!" % who


if __name__ == "__main__":
    serve(Hello, server_name="{name}")
