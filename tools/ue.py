#!/usr/bin/env python3
"""Client da terminale per il server MCP ufficiale di Unreal (UE 5.8).

Esempi:
  tools/ue.py stato                          # il server risponde?
  tools/ue.py toolsets                       # elenco dei toolset
  tools/ue.py descrivi EditorToolset.EditorAppToolset
  tools/ue.py chiama EditorToolset.EditorAppToolset.CaptureViewport '{"...": ...}'
  tools/ue.py py 'result = unreal.SystemLibrary.get_engine_version()'
  tools/ue.py pyfile /percorso/assoluto/script.py
  tools/ue.py foto docs/progressi/viewport.png  # cattura del viewport su file
  tools/ue.py pie start [--menu|--continue]|stop   # Play In Editor (starts a new campaign unless --menu)
  tools/ue.py pie cmd 'astra.say Red alert.' 'astra.battle.time 168'   # comandi console nel mondo di gioco

Le risposte con immagini in base64 vengono salvate su file (non stampate).
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("ASTRA_MCP_URL", "http://127.0.0.1:8000/mcp")
PROTO = "2025-11-25"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_FILE = os.path.join(ROOT, ".astra", "mcp_session")
AGENT_TOOLSET = "astra_agent_tools.AstraAgentTools"


class McpError(RuntimeError):
    pass


def _post(payload, session=None, timeout=900):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": PROTO}
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        ctype = resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8", "replace")
    if not body.strip():
        return sid, None
    if "text/event-stream" in ctype:
        msg = None
        for line in body.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    obj = json.loads(data)
                    if "result" in obj or "error" in obj:
                        msg = obj
        return sid, msg
    return sid, json.loads(body)


def _session(force_new=False):
    if not force_new and os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as fh:
            return fh.read().strip()
    sid, msg = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": PROTO, "capabilities": {},
                                 "clientInfo": {"name": "astra-cli", "version": "0.1"}}})
    if msg and "error" in msg:
        raise McpError(msg["error"])
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session=sid)
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, "w") as fh:
        fh.write(sid or "")
    return sid


def rpc(method, params=None, timeout=900):
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10**9, "method": method}
    if params is not None:
        payload["params"] = params
    for attempt in (0, 1):
        sid = _session(force_new=attempt == 1)
        try:
            _, msg = _post(payload, session=sid, timeout=timeout)
        except urllib.error.HTTPError as err:
            if err.code in (400, 404) and attempt == 0:
                continue  # sessione scaduta: ne apro una nuova
            raise
        if msg and "error" in msg:
            raise McpError(json.dumps(msg["error"], ensure_ascii=False))
        return (msg or {}).get("result")
    raise McpError("sessione MCP non valida")


def call_tool(name, arguments=None, timeout=900):
    return rpc("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)


def toolset_call(qualified, arguments=None, timeout=900):
    """Chiama uno strumento di un toolset: 'Toolset.Nome.strumento' -> toolset_name + tool_name."""
    toolset, _, tool = qualified.rpartition(".")
    params = {"tool_name": tool, "arguments": arguments or {}}
    if toolset:
        params["toolset_name"] = toolset
    return call_tool("call_tool", params, timeout=timeout)


def _save_images(obj, out_path=None):
    """Salva su file le immagini base64 trovate nel risultato; restituisce l'oggetto ripulito."""
    saved = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if isinstance(v, str) and len(v) > 2000 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", v[:4000]):
                    try:
                        raw = base64.b64decode(v)
                    except Exception:  # pylint: disable=broad-except
                        continue
                    if raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:3] == b"\xff\xd8\xff":
                        ext = ".png" if raw[:4] == b"\x89PNG" else ".jpg"
                        path = out_path or os.path.join(ROOT, ".astra", f"cattura_{int(time.time()*1000)}{ext}")
                        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                        with open(path, "wb") as fh:
                            fh.write(raw)
                        saved.append(path)
                        o[k] = f"<immagine salvata: {path}>"
                        continue
                walk(v)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(obj)
    return obj, saved


def _unwrap(result):
    """Estrae il testo/JSON utile da un risultato MCP tools/call."""
    if not isinstance(result, dict):
        return result
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except Exception:  # pylint: disable=broad-except
        return joined if joined else result


def agent_python(code, timeout=900):
    res = toolset_call(f"{AGENT_TOOLSET}.run_python", {"code": code}, timeout=timeout)
    return _unwrap(res)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd, args = argv[1], argv[2:]
    try:
        if cmd == "stato":
            res = rpc("tools/list", {}, timeout=15)
            names = [t["name"] for t in (res or {}).get("tools", [])]
            print("MCP attivo. Strumenti di primo livello:", ", ".join(names))
        elif cmd == "toolsets":
            print(json.dumps(_unwrap(call_tool("list_toolsets")), indent=1, ensure_ascii=False)[:20000])
        elif cmd == "descrivi":
            print(json.dumps(_unwrap(call_tool("describe_toolset", {"toolset_name": args[0]})),
                             indent=1, ensure_ascii=False)[:60000])
        elif cmd == "chiama":
            tool = args[0]
            arguments = json.loads(args[1]) if len(args) > 1 else {}
            out = args[2] if len(args) > 2 else None
            res = _unwrap(toolset_call(tool, arguments))
            res, saved = _save_images(res, out)
            print(json.dumps(res, indent=1, ensure_ascii=False)[:60000] if not isinstance(res, str) else res[:60000])
            for p in saved:
                print("IMMAGINE:", p)
        elif cmd == "py":
            print(agent_python(args[0]))
        elif cmd == "pyfile":
            res = toolset_call(f"{AGENT_TOOLSET}.run_python_file", {"path": os.path.abspath(args[0])})
            print(_unwrap(res))
        elif cmd == "pie":
            sub, rest = args[0], args[1:]
            if sub == "start":
                # the title menu waits for a choice: tests start a campaign at once (--menu to see the menu,
                # --continue to resume the saved one)
                mode = None if "--menu" in rest else ("continue" if "--continue" in rest else "new")
                code = ("les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)\n"
                        "if not unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world():\n"
                        "    les.editor_request_begin_play()\n"
                        "print('PIE richiesto')")
                print(agent_python("import unreal\n" + code))
                if mode:
                    import time as _t
                    for _ in range(40):
                        _t.sleep(0.5)
                        r = agent_python("import unreal\nw = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()\n"
                                         f"print('ok' if w else 'no')\nif w: unreal.SystemLibrary.execute_console_command(w, 'astra.campaign {mode}')")
                        if "ok" in str(r):
                            break
                return 0
            elif sub == "stop":
                code = ("if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world():\n"
                        "    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()\n"
                        "print('PIE fermato')")
            elif sub == "cmd":
                code = ("w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()\n"
                        "assert w, 'PIE non attivo'\n"
                        f"for c in {rest!r}:\n"
                        "    unreal.SystemLibrary.execute_console_command(w, c)\n"
                        "print('ok')")
            else:
                print("uso: pie start|stop|cmd <comando>...")
                return 1
            print(agent_python("import unreal\n" + code))
        elif cmd == "foto":
            out = os.path.abspath(args[0] if args else os.path.join(ROOT, ".astra", "viewport.png"))
            cam = _unwrap(toolset_call("EditorToolset.EditorAppToolset.GetCameraTransform", {}))
            cam = cam.get("returnValue", cam) if isinstance(cam, dict) else cam
            params = {"captureTransform": cam, "bShowUI": False,
                      "annotations": {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0,
                                      "maxLabelDistance": 0, "classFilter": None, "maxLabels": 0}}
            res = _unwrap(toolset_call("EditorToolset.EditorAppToolset.CaptureViewport", params))
            res, saved = _save_images(res, out)
            print("\n".join(f"IMMAGINE: {p}" for p in saved) or json.dumps(res, ensure_ascii=False)[:4000])
        else:
            print("comando sconosciuto:", cmd)
            return 1
    except urllib.error.URLError as err:
        print("Server MCP non raggiungibile (l'editor è aperto con il server attivo?):", err)
        return 2
    except McpError as err:
        print("Errore MCP:", err)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
