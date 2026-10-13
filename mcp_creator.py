"""mcp_creator: make a small MCP server from a few Python classes.

One file, standard library only, Python 3.8 or newer. No Sublime Text needed.

    from mcp_creator import Tool, arg, opt, serve

    class Weather(Tool):
        name = "get_weather"                      # optional, defaults to the class name
        desc = "Get current weather for a city"   # optional, defaults to the docstring
        city = arg(str, "City name")              # required argument
        units = opt(str, "c or f", default="c", choices=["c", "f"])   # optional argument

        def call(self, city, units="c"):
            return "Weather in %s: 20 %s, sunny" % (city, units.upper())

    serve(Weather, server_name="my_tools")

Run it as a plain script and add it to a client, for example:

    claude mcp add my-tools python weather.py

``python weather.py --list`` prints the tool list as JSON instead of serving.

The server speaks MCP over standard input and output (one JSON message per line).
Everything a tool prints must go to stderr; stdout belongs to the protocol.
"""

import base64
import itertools
import json
import mimetypes
import re
import sys
import traceback

__version__ = "0.1.0"

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

_TYPE_NAMES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
_counter = itertools.count()
_MISSING = object()


class _Param(object):
    def __init__(self, type_, help_, required, default, choices):
        if type_ not in _TYPE_NAMES:
            raise TypeError("argument type must be one of str, int, float, bool, list, dict (got %r)" % (type_,))
        self.type = type_
        self.help = help_
        self.required = required
        self.default = default
        self.choices = list(choices) if choices else None
        self.name = None
        self._n = next(_counter)

    def schema(self):
        s = {"type": _TYPE_NAMES[self.type]}
        if self.help:
            s["description"] = self.help
        if self.choices:
            s["enum"] = self.choices
        if self.default is not _MISSING and self.default is not None:
            s["default"] = self.default
        return s


def arg(type=str, help="", choices=None):
    """A required argument of a tool."""
    return _Param(type, help, True, _MISSING, choices)


def opt(type=str, help="", default=None, choices=None):
    """An optional argument. If the client leaves it out, `default` is passed to call()."""
    return _Param(type, help, False, default, choices)


def _snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class _ToolMeta(type):
    def __new__(mcs, cls_name, bases, ns):
        cls = super().__new__(mcs, cls_name, bases, ns)
        params = {}
        for base in reversed(cls.__mro__[1:]):
            params.update(getattr(base, "_params", {}))
        own = sorted(((k, v) for k, v in ns.items() if isinstance(v, _Param)), key=lambda kv: kv[1]._n)
        for key, param in own:
            param.name = key
            params[key] = param
        cls._params = params
        return cls


class Tool(metaclass=_ToolMeta):
    """Base class of a tool. Set `name` and `desc` (both optional), declare arguments with
    arg() and opt(), and implement call(). call() receives the arguments as keyword arguments."""

    name = None
    desc = None

    def call(self, **kwargs):
        raise NotImplementedError("%s does not implement call()" % type(self).__name__)

    @classmethod
    def tool_name(cls):
        return cls.name or _snake(cls.__name__)

    @classmethod
    def description(cls):
        if cls.desc:
            return cls.desc
        doc = (cls.__doc__ or "").strip()
        return doc.split("\n\n")[0].replace("\n", " ").strip() if doc else cls.tool_name()

    @classmethod
    def input_schema(cls):
        return {
            "type": "object",
            "properties": {k: p.schema() for k, p in cls._params.items()},
            "required": [k for k, p in cls._params.items() if p.required],
            "additionalProperties": False,
        }

    @classmethod
    def listing(cls):
        return {"name": cls.tool_name(), "description": cls.description(), "inputSchema": cls.input_schema()}


def text(value):
    """A text content part."""
    return {"type": "text", "text": str(value)}


def _binary(kind, data, mime):
    if isinstance(data, str):
        with open(data, "rb") as f:
            raw = f.read()
        mime = mime or mimetypes.guess_type(data)[0]
    else:
        raw = bytes(data)
    if not mime:
        raise ValueError("give the mime type for raw bytes, for example mime='image/png'")
    return {"type": kind, "mimeType": mime, "data": base64.b64encode(raw).decode("ascii")}


def image(data, mime=None):
    """An image content part from a file path or bytes."""
    return _binary("image", data, mime)


def audio(data, mime=None):
    """An audio content part from a file path or bytes."""
    return _binary("audio", data, mime)


def _content(result):
    """Turn whatever call() returned into the `content` list of a tools/call result."""
    if result is None:
        return [text("")]
    if isinstance(result, str):
        return [text(result)]
    if isinstance(result, (list, tuple)) and result and all(isinstance(p, dict) and "type" in p for p in result):
        return list(result)
    if isinstance(result, dict) and "type" in result:
        return [result]
    if isinstance(result, (dict, list, tuple)):
        return [text(json.dumps(result, indent=2, ensure_ascii=False, default=str))]
    return [text(result)]


def _type_ok(value, type_):
    if type_ is bool:
        return isinstance(value, bool)
    if type_ is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if type_ is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type_)


def _bind(tool_cls, arguments):
    """Check the arguments against the declared ones and fill in defaults. Returns (kwargs, error)."""
    arguments = arguments or {}
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    unknown = sorted(set(arguments) - set(tool_cls._params))
    if unknown:
        return None, "unknown argument(s): " + ", ".join(unknown)
    kwargs = {}
    for key, p in tool_cls._params.items():
        if key in arguments:
            value = arguments[key]
            if not _type_ok(value, p.type):
                return None, "argument %r must be %s" % (key, _TYPE_NAMES[p.type])
            if p.choices and value not in p.choices:
                return None, "argument %r must be one of %s" % (key, ", ".join(map(str, p.choices)))
            kwargs[key] = value
        elif p.required:
            return None, "missing required argument %r" % key
        elif p.default is not _MISSING:
            kwargs[key] = p.default
    return kwargs, None


class _Server(object):
    def __init__(self, tools, server_name, version, instructions):
        self.tools = {}
        for t in tools:
            if not (isinstance(t, type) and issubclass(t, Tool)):
                raise TypeError("serve() takes Tool subclasses, got %r" % (t,))
            name = t.tool_name()
            if name in self.tools:
                raise ValueError("two tools are named %r" % name)
            self.tools[name] = t
        self.server_name = server_name
        self.version = version
        self.instructions = instructions

    def handle(self, msg):
        """Return the response message for one request, or None for a notification."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method is None:
            return None  # a response from the client; nothing to do
        if mid is None:
            return None  # notification (notifications/initialized, notifications/cancelled, ...)
        if method == "initialize":
            wanted = params.get("protocolVersion")
            result = {
                "protocolVersion": wanted if wanted in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.server_name, "version": self.version},
            }
            if self.instructions:
                result["instructions"] = self.instructions
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [t.listing() for t in self.tools.values()]}}
        if method == "tools/call":
            tool_cls = self.tools.get(params.get("name"))
            if tool_cls is None:
                return _error(mid, -32602, "unknown tool: %s" % params.get("name"))
            kwargs, problem = _bind(tool_cls, params.get("arguments"))
            if problem:
                return _error(mid, -32602, problem)
            try:
                content = _content(tool_cls().call(**kwargs))
                return {"jsonrpc": "2.0", "id": mid, "result": {"content": content, "isError": False}}
            except Exception as e:  # a tool that fails reports it as a tool result, not a protocol error
                traceback.print_exc(file=sys.stderr)
                return {"jsonrpc": "2.0", "id": mid,
                        "result": {"content": [text("%s: %s" % (type(e).__name__, e))], "isError": True}}
        return _error(mid, -32601, "method not found: %s" % method)


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def serve(*tools, server_name="mcp_creator", version="0.1.0", instructions=None):
    """Serve the given Tool subclasses over standard input and output until the client closes it."""
    server = _Server(tools, server_name, version, instructions)
    if "--list" in sys.argv[1:]:
        print(json.dumps({"tools": [t.listing() for t in server.tools.values()]}, indent=2, ensure_ascii=False))
        return
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n" if stream is sys.stdout else None)
        except (AttributeError, ValueError):
            pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _send(_error(None, -32700, "parse error"))
            continue
        response = server.handle(msg)
        if response is not None:
            _send(response)
