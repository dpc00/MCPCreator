"""Sublime Text helper for MCP Creator: scaffold, test and register small MCP servers.

Commands (command palette, "MCP Creator: ..."):
  New Tool Server    make a new server script (plus a copy of mcp_creator.py beside it) and open it
  Add Tool           insert a tool class at the cursor
  Test Server        start the open file as an MCP server, ask it for its tools, show them
  Copy Add Command   copy the `claude mcp add ...` line for the open file

Nothing here depends on sublime-mcp. The servers it makes are plain Python scripts.
"""

import json
import os
import re
import subprocess
import threading

import sublime
import sublime_plugin

PKG = __name__.split(".")[0]
SETTINGS = "MCP Creator.sublime-settings"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PANEL = "mcp_creator"


def _settings():
    return sublime.load_settings(SETTINGS)


def _tools_folder():
    return _settings().get("tools_folder") or os.path.join(sublime.packages_path(), "User", "MCP Tools")


def _python():
    return _settings().get("python") or "python"


def _resource(rel):
    return sublime.load_resource("Packages/%s/%s" % (PKG, rel))


def _status(message):
    sublime.status_message("MCP Creator: " + message)


class McpCreatorNewServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel("New MCP server name:", "my_tools", self.on_done, None, None)

    def on_done(self, name):
        name = name.strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", name):
            sublime.error_message("MCP Creator: use letters, digits, _ and - only, starting with a letter.")
            return
        folder = _tools_folder()
        os.makedirs(folder, exist_ok=True)
        script = os.path.join(folder, name.replace("-", "_") + ".py")
        if not os.path.exists(script):
            text = _resource("templates/server_template.py")
            text = text.replace("{name}", name.replace("-", "_")).replace("{dashname}", name.replace("_", "-"))
            with open(script, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        library = os.path.join(folder, "mcp_creator.py")
        if not os.path.exists(library):
            with open(library, "w", encoding="utf-8", newline="\n") as f:
                f.write(_resource("mcp_creator.py"))
        self.window.open_file(script)
        _status("opened " + script)


class McpCreatorAddToolCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        view.run_command("insert_snippet", {"name": "Packages/%s/Snippets/tool.sublime-snippet" % PKG})

    def is_enabled(self):
        return self.window.active_view() is not None


def _active_script(window):
    view = window.active_view()
    if view is None or not view.file_name():
        _status("open and save the server script first")
        return None
    return view


class McpCreatorCopyAddCommandCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _active_script(self.window)
        if view is None:
            return
        path = view.file_name()
        name = os.path.splitext(os.path.basename(path))[0].replace("_", "-")
        sublime.set_clipboard('claude mcp add %s python "%s"' % (name, path))
        _status("copied: claude mcp add %s python ..." % name)

    def is_enabled(self):
        return self.window.active_view() is not None


def _probe(python, path):
    """Start the script as an MCP server, do the handshake, ask for the tools. Returns text to show."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcp-creator-test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    try:
        done = subprocess.run([python, path], input=payload, capture_output=True, text=True, encoding="utf-8",
                              timeout=20, cwd=os.path.dirname(path), creationflags=NO_WINDOW)
    except FileNotFoundError:
        return "Could not start %r. Set \"python\" in the MCP Creator settings." % python
    except subprocess.TimeoutExpired:
        return "The server did not answer within 20 seconds."
    answers = {}
    stray = []
    for line in done.stdout.splitlines():
        try:
            msg = json.loads(line)
            answers[msg.get("id")] = msg
        except ValueError:
            stray.append(line)
    lines = ["MCP Creator test of " + path, ""]
    init = answers.get(1)
    if init and "result" in init:
        info = init["result"].get("serverInfo", {})
        lines.append("Server: %s %s (protocol %s)" % (info.get("name", "?"), info.get("version", ""), init["result"].get("protocolVersion")))
    else:
        lines.append("No answer to initialize.")
    listing = answers.get(2)
    if listing and "result" in listing:
        tools = listing["result"].get("tools", [])
        lines.append("Tools: %d" % len(tools))
        for t in tools:
            schema = t.get("inputSchema", {})
            required = set(schema.get("required", []))
            args = ", ".join("%s%s: %s" % (k, "" if k in required else "?", v.get("type", "?")) for k, v in schema.get("properties", {}).items())
            lines.append("  %s(%s)" % (t.get("name"), args))
            if t.get("description"):
                lines.append("      " + t["description"])
    else:
        lines.append("No tool list received.")
    if stray:
        lines += ["", "Lines on stdout that are not MCP messages (a tool must print to stderr, not stdout):"] + ["  " + s for s in stray[:10]]
    if done.stderr.strip():
        lines += ["", "stderr:", done.stderr.strip()[-1500:]]
    if done.returncode not in (0, None):
        lines += ["", "The script exited with code %s." % done.returncode]
    return "\n".join(lines)


class McpCreatorTestServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _active_script(self.window)
        if view is None:
            return
        if view.is_dirty():
            _status("save the file first; the test runs the file on disk")
            return
        path = view.file_name()
        python = _python()
        window = self.window
        _status("testing " + os.path.basename(path))

        def work():
            result = _probe(python, path)
            sublime.set_timeout(lambda: self.show(window, result), 0)

        threading.Thread(target=work, daemon=True).start()

    def show(self, window, text):
        panel = window.create_output_panel(PANEL)
        panel.set_read_only(False)
        panel.run_command("append", {"characters": text + "\n"})
        panel.set_read_only(True)
        window.run_command("show_panel", {"panel": "output." + PANEL})

    def is_enabled(self):
        return self.window.active_view() is not None
