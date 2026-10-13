"""A two-tool example server. Run: python examples/hello.py --list
Add it to Claude Code: claude mcp add hello python C:\\path\\to\\examples\\hello.py"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mcp_creator import Tool, arg, opt, serve


class Greet(Tool):
    """Say hello to someone."""

    who = arg(str, "Who to greet")
    shout = opt(bool, "Upper-case the greeting", default=False)

    def call(self, who, shout=False):
        message = "Hello, %s!" % who
        return message.upper() if shout else message


class CurrentTime(Tool):
    name = "current_time"
    desc = "The current local time on this computer"
    style = opt(str, "Format", default="iso", choices=["iso", "clock"])

    def call(self, style="iso"):
        return time.strftime("%Y-%m-%dT%H:%M:%S" if style == "iso" else "%H:%M")


if __name__ == "__main__":
    serve(Greet, CurrentTime, server_name="hello")
