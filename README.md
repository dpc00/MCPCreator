# MCP Creator

Make a small MCP server from a few Python classes. One file (`mcp_creator.py`), standard library only, Python 3.8 or newer. It does not need Sublime Text or sublime-mcp.

```python
from mcp_creator import Tool, arg, opt, serve

class Greet(Tool):
    """Say hello to someone."""

    who = arg(str, "Who to greet")                       # required
    shout = opt(bool, "Upper-case it", default=False)    # optional

    def call(self, who, shout=False):
        message = "Hello, %s!" % who
        return message.upper() if shout else message

serve(Greet, server_name="hello")
```

Run it as a script and add it to a client:

```
claude mcp add hello python path\to\hello.py
python hello.py --list        # print the tool list as JSON instead of serving
```

- A tool is a `Tool` subclass. `name` defaults to the class name in snake_case, `desc` to the first paragraph of the docstring.
- `arg(type, help, choices=None)` is required, `opt(type, help, default=None, choices=None)` is optional. Types: `str`, `int`, `float`, `bool`, `list`, `dict`. The arguments are checked before `call()` runs; a bad call gets a JSON-RPC error.
- `call()` may return a string (text), a dict or list (shown as JSON text), or a list of content parts. `image(path_or_bytes)` and `audio(path_or_bytes)` build image and audio parts. An exception inside `call()` comes back to the client as a tool error (`isError`), with the traceback on stderr.
- Messages are one JSON object per line on standard input and output. Print only to stderr from a tool: stdout belongs to the protocol.

## Sublime Text helper

The same folder is a Sublime Text package ("MCP Creator"). It only helps you write servers; the servers it makes are plain Python scripts and do not need Sublime or sublime-mcp. Command palette:

- **MCP Creator: New Tool Server** asks for a name and writes `<name>.py` (with a copy of `mcp_creator.py` next to it, so it runs anywhere) into `Packages/User/MCP Tools` (change with the `tools_folder` setting), then opens it.
- **MCP Creator: Add Tool** inserts a tool class at the cursor (also available as the `mcptool` snippet in Python files). Put the new class in the `serve(...)` call.
- **MCP Creator: Test Server** starts the open (saved) file as an MCP server, does the handshake and shows the server name and its tools with their arguments in an output panel. It warns about anything the script prints to stdout, which breaks the protocol.
- **MCP Creator: Copy Add Command** copies `claude mcp add <name> python "<path>"` for the open file.

Set `python` in `MCP Creator.sublime-settings` if `python` is not on the PATH Sublime sees.

## Status

First version. Tried for real: the handshake, `tools/list`, `tools/call` and the error cases over a pipe against `examples/hello.py`; Claude Code 2.1.296 (headless, `--mcp-config`) called tools of both `examples/hello.py` and a server made with the Sublime commands (New Tool Server, then Add Tool, then Test Server; the answer came back as written). The Sublime commands were tried in Sublime Text build 4200 on Windows only. Not yet submitted to Package Control.

Inspired by [tiny_mcp](https://github.com/maxim/tiny_mcp) (Ruby) by Max Chernyak.
