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

Status: first version. Handshake, `tools/list`, `tools/call` and the error cases were tried by hand against `examples/hello.py` over a pipe; it has not yet been tried with a real client. A Sublime Text helper package (scaffolding, a test panel) is planned and not written.

Inspired by [tiny_mcp](https://github.com/maxim/tiny_mcp) (Ruby) by Max Chernyak.
