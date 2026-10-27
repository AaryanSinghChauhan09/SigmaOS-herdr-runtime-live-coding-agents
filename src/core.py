"""Live-coding agent runtime for SigmaOS-herdr-runtime-live-coding-agents
(inspired by herdr).

Principles: every spawn/stop is planned as pure argv first (self_test never
touches tmux, agents or PIDs), session state is schema-validated fail-fast with
unique ids, tool access is a whitelist (defensive by default), deterministic
summaries.
"""
import argparse, json, re, shlex, sys

ENGINE = {
    "name": "sigma-herdr",
    "summary": "Live-coding agent runtime: spawn, sessions, tool allowlists, stop",
    "language": "python",
    "verbs": ["spawn-plan", "session", "tools", "stop-plan"],
    "principles": ["Separation of Concerns", "Defensive Programming",
                   "Fail-Fast", "Least Astonishment", "KISS",
                   "Deterministic Testing"],
}

cli_doc = """\
$ sigma-herdr spawn-plan --agent claude --session webapp --cwd ~/src/webapp --mux tmux
$ sigma-herdr session sessions.json
$ sigma-herdr tools --profile read-only
$ sigma-herdr tools --profile standard --config
$ sigma-herdr stop-plan --session webapp --pid 4242 --grace 5
"""

AGENTS = ("aider", "claude", "codex", "gemini", "goose", "opencode")
MUXES = ("tmux", "zellij", "none")
STATUSES = ("running", "stopped", "error")
KNOWN_TOOLS = ("bash", "edit", "glob", "grep", "list", "patch", "read", "run",
               "search", "test", "todo", "webfetch", "websearch", "write")
PROFILES = {
    "read-only": ("glob", "grep", "list", "read", "search", "webfetch",
                  "websearch"),
    "standard": ("bash", "edit", "glob", "grep", "list", "patch", "read",
                 "run", "search", "test", "todo", "webfetch", "websearch",
                 "write"),
    "full": KNOWN_TOOLS,
}

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$")


class HerdrError(ValueError):
    pass


def _check_session(sid):
    if not isinstance(sid, str) or not _SESSION_ID_RE.match(sid):
        raise HerdrError(f"bad session id: {sid!r}")
    return sid


def _check_path(path, what="path"):
    if not isinstance(path, str) or not path.strip():
        raise HerdrError(f"empty {what}")
    if "\x00" in path or "\n" in path:
        raise HerdrError(f"{what} must be a single line without NUL bytes")
    return path


# --------------------------------------------------------------------------- #
#  Spawn plan (pure argv)
# --------------------------------------------------------------------------- #
def spawn_plan(agent, session, cwd, files=(), tty=True, mux="tmux", model=None):
    """Build the argv for a live-coding agent session. Never executed here."""
    if agent not in AGENTS:
        raise HerdrError(f"unknown agent {agent!r} (have: {', '.join(AGENTS)})")
    _check_session(session)
    _check_path(cwd, "cwd")
    if mux not in MUXES:
        raise HerdrError(f"unknown mux {mux!r} (have: {', '.join(MUXES)})")
    if model is not None:
        if not isinstance(model, str) or not _MODEL_RE.match(model):
            raise HerdrError(f"bad model id: {model!r}")
    argv = ["herdr", "spawn", "--agent", agent, "--session", session,
            "--cwd", cwd]
    if model:
        argv += ["--model", model]
    if mux != "none":
        argv += ["--mux", mux]
    argv += ["--tty"] if tty else ["--headless"]
    seen, extra = set(), []
    for f in files:
        _check_path(f, "file")
        if f in seen:
            raise HerdrError(f"duplicate file: {f!r}")
        seen.add(f)
        extra.append(f)
    if extra:
        argv += ["--"] + extra
    return {"agent": agent, "session": session, "argv": argv, "cwd": cwd,
            "tty": bool(tty), "mux": mux, "model": model,
            "files": list(extra)}


# --------------------------------------------------------------------------- #
#  Session state parsing (pure)
# --------------------------------------------------------------------------- #
def parse_sessions(text):
    """Parse and validate a herdr session-state JSON document."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise HerdrError(f"session state is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise HerdrError("session state must be a JSON object")
    rows = data.get("sessions")
    if not isinstance(rows, list):
        raise HerdrError('session state needs a "sessions" list')
    out, seen = [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HerdrError(f"session #{i} is not an object")
        sid = row.get("id")
        try:
            _check_session(sid)
        except HerdrError as e:
            raise HerdrError(f"session #{i}: {e}") from e
        if sid in seen:
            raise HerdrError(f"duplicate session id: {sid!r}")
        seen.add(sid)
        agent = row.get("agent")
        if agent not in AGENTS:
            raise HerdrError(f"{sid}: unknown agent {agent!r}")
        status = row.get("status")
        if status not in STATUSES:
            raise HerdrError(f"{sid}: bad status {status!r}")
        pid = row.get("pid")
        if pid is not None and (not isinstance(pid, int)
                                or isinstance(pid, bool) or pid <= 0):
            raise HerdrError(f"{sid}: bad pid {pid!r}")
        cwd = row.get("cwd", "")
        _check_path(cwd, f"session {sid} cwd")
        out.append({"id": sid, "agent": agent, "status": status, "pid": pid,
                    "cwd": cwd})
    return out


def summarize(sessions):
    counts = {"running": 0, "stopped": 0, "error": 0}
    for s in sessions:
        counts[s["status"]] += 1
    counts["total"] = len(sessions)
    return counts


# --------------------------------------------------------------------------- #
#  Tool allowlists (pure)
# --------------------------------------------------------------------------- #
def list_tools(profile):
    if profile not in PROFILES:
        raise HerdrError(f"unknown profile {profile!r} "
                         f"(have: {', '.join(sorted(PROFILES))})")
    return sorted(PROFILES[profile])


def tools_config(tools):
    """Deterministic JSON allowlist config from an iterable of tool names."""
    if isinstance(tools, str) or not isinstance(tools, (list, tuple, set, frozenset)):
        raise HerdrError("tools must be a list of names")
    seen = []
    for t in tools:
        if not isinstance(t, str) or t not in KNOWN_TOOLS:
            raise HerdrError(f"unknown tool {t!r} "
                             f"(have: {', '.join(KNOWN_TOOLS)})")
        if t not in seen:
            seen.append(t)  # de-duplicate, keep first-seen order
    if not seen:
        raise HerdrError("empty tool allowlist")
    ordered = sorted(seen)
    return json.dumps({"tools": ordered}, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- #
#  Stop plan (pure argv, signal escalation)
# --------------------------------------------------------------------------- #
def stop_plan(session, pid=None, grace=5, mux="tmux"):
    """Escalation plan: SIGTERM, wait `grace`, then SIGKILL (or mux kill)."""
    _check_session(session)
    if not isinstance(grace, int) or isinstance(grace, bool) or not 0 <= grace <= 120:
        raise HerdrError(f"grace must be 0..120 seconds, got {grace!r}")
    if pid is None:
        if mux not in ("tmux", "zellij"):
            raise HerdrError(f"pid-less stop needs a mux (tmux|zellij), got {mux!r}")
        argv = (["tmux", "kill-session", "-t", session] if mux == "tmux"
                else ["zellij", "delete-session", session])
        return {"session": session, "grace": grace,
                "steps": [{"signal": None, "delay": 0, "argv": argv}]}
    if not isinstance(pid, int) or isinstance(pid, bool) or not 1 <= pid <= 2 ** 31 - 1:
        raise HerdrError(f"bad pid: {pid!r}")
    return {"session": session, "grace": grace, "pid": pid, "steps": [
        {"signal": "SIGTERM", "delay": 0,
         "argv": ["kill", "-TERM", str(pid)]},
        {"signal": "SIGKILL", "delay": grace,
         "argv": ["kill", "-KILL", str(pid)]},
    ]}


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("spawn-plan", help="build the herdr spawn argv")
    sp.add_argument("--agent", required=True, choices=AGENTS)
    sp.add_argument("--session", required=True)
    sp.add_argument("--cwd", required=True)
    sp.add_argument("--file", action="append", default=[], dest="files")
    sp.add_argument("--model", default=None)
    sp.add_argument("--mux", default="tmux", choices=MUXES)
    sp.add_argument("--headless", action="store_true")
    se = sub.add_parser("session", help="parse & summarise a session-state file")
    se.add_argument("file")
    tl = sub.add_parser("tools", help="list or export a tool allowlist")
    tl.add_argument("--profile", default="standard", choices=sorted(PROFILES))
    tl.add_argument("--config", action="store_true", help="print JSON config")
    st = sub.add_parser("stop-plan", help="build the stop/escalation plan")
    st.add_argument("--session", required=True)
    st.add_argument("--pid", type=int, default=None)
    st.add_argument("--grace", type=int, default=5)
    st.add_argument("--mux", default="tmux", choices=("tmux", "zellij"))
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "spawn-plan":
            plan = spawn_plan(args.agent, args.session, args.cwd,
                              files=args.files, tty=not args.headless,
                              mux=args.mux, model=args.model)
            print(shlex.join(plan["argv"]))
        elif args.cmd == "session":
            with open(args.file, "r", encoding="utf-8") as fh:
                sessions = parse_sessions(fh.read())
            for s in sessions:
                pid = s["pid"] if s["pid"] is not None else "-"
                print(f"{s['id']:<20} {s['agent']:<8} {s['status']:<8} "
                      f"pid={pid}  {s['cwd']}")
            counts = summarize(sessions)
            print(f"total={counts['total']} running={counts['running']} "
                  f"stopped={counts['stopped']} error={counts['error']}")
        elif args.cmd == "tools":
            if args.config:
                sys.stdout.write(tools_config(list_tools(args.profile)))
            else:
                for t in list_tools(args.profile):
                    print(t)
        elif args.cmd == "stop-plan":
            plan = stop_plan(args.session, args.pid, args.grace, args.mux)
            for step in plan["steps"]:
                sig = step["signal"] or "-"
                if step["delay"]:
                    print(f"sleep {step['delay']}  # between signals")
                print(f"{sig:<8} {shlex.join(step['argv'])}")
        return 0
    except (HerdrError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    # --- spawn plan (pure argv) --------------------------------------------
    p = spawn_plan("claude", "webapp", "/home/u/src/webapp",
                   files=["src/app.py", "README.md"])
    assert p["argv"] == [
        "herdr", "spawn", "--agent", "claude", "--session", "webapp",
        "--cwd", "/home/u/src/webapp", "--mux", "tmux", "--tty",
        "--", "src/app.py", "README.md"], p["argv"]
    headless = spawn_plan("aider", "s1", "/w", tty=False, mux="none",
                          model="gpt-4.1-mini")
    assert "--headless" in headless["argv"] and "--mux" not in headless["argv"]
    assert headless["argv"][headless["argv"].index("--model") + 1] == "gpt-4.1-mini"
    assert spawn_plan("codex", "s2", "/w") == spawn_plan("codex", "s2", "/w")
    for bad_call in ((spawn_plan, ("vim", "s", "/w")),            # unknown agent
                     (spawn_plan, ("claude", "../etc", "/w")),    # traversal id
                     (spawn_plan, ("claude", "a b", "/w")),       # space id
                     (spawn_plan, ("claude", "", "/w")),
                     (spawn_plan, ("claude", "s", "")),           # empty cwd
                     (spawn_plan, ("claude", "s", "/w\n/x")),
                     (spawn_plan, ("claude", "s", "/w", ["a", "a"])),  # dup file
                     (spawn_plan, ("claude", "s", "/w", ["bad\nfile"])),
                     (spawn_plan, ("claude", "s", "/w", (), True, "screen")),
                     (spawn_plan, ("claude", "s", "/w", (), True, "tmux",
                                   "bad model!"))):
        try:
            bad_call[0](*bad_call[1])
        except HerdrError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")

    # --- session state parsing ---------------------------------------------
    STATE = """{
      "version": 1,
      "sessions": [
        {"id": "webapp", "agent": "claude", "status": "running",
         "pid": 4242, "cwd": "/home/u/src/webapp"},
        {"id": "docs", "agent": "aider", "status": "stopped",
         "pid": null, "cwd": "/home/u/docs"}
      ]
    }"""
    sessions = parse_sessions(STATE)
    assert [s["id"] for s in sessions] == ["webapp", "docs"]
    assert sessions[0]["pid"] == 4242 and sessions[1]["pid"] is None
    counts = summarize(sessions)
    assert counts == {"running": 1, "stopped": 1, "error": 0, "total": 2}, counts
    assert summarize([]) == {"running": 0, "stopped": 0, "error": 0, "total": 0}
    def _state(rows):
        return json.dumps({"sessions": rows})

    good_row = {"id": "a", "agent": "claude", "status": "running",
                "pid": 1, "cwd": "/w"}
    bad_states = [
        "not json",                                   # not JSON
        "[]",                                         # not an object
        '{"sessions": {}}',                           # not a list
        # duplicate id
        _state([good_row,
                {"id": "a", "agent": "aider", "status": "running",
                 "pid": 2, "cwd": "/w"}]),
        _state([{**good_row, "agent": "vim"}]),       # unknown agent
        _state([{**good_row, "status": "busy"}]),     # bad status
        _state([{**good_row, "pid": "42"}]),          # bad pid
        _state([{**good_row, "pid": 0}]),             # pid 0
        _state([{"agent": "claude", "status": "running",
                 "pid": 1, "cwd": "/w"}]),            # missing id
        _state([{"id": "a", "agent": "claude",
                 "status": "running", "pid": 1}]),    # missing cwd
    ]
    for bad in bad_states:
        try:
            parse_sessions(bad)
        except HerdrError:
            pass
        else:
            raise AssertionError(f"session state should have been rejected: {bad}")

    # --- tool allowlists ----------------------------------------------------
    ro = list_tools("read-only")
    assert "read" in ro and "grep" in ro and "bash" not in ro and "write" not in ro
    std = list_tools("standard")
    assert "bash" in std and "write" in std
    assert ro == sorted(ro) and list_tools("full") == sorted(KNOWN_TOOLS)
    cfg = json.loads(tools_config(ro))
    assert cfg["tools"] == sorted(ro)
    assert tools_config(["read", "read", "grep"]) == \
        tools_config(["grep", "read"])          # de-duped + deterministic
    for bad_call in ((list_tools, ("root",)),
                     (tools_config, (["rm-system"],)),     # unknown tool
                     (tools_config, (["read", "not-a-tool"],)),
                     (tools_config, ((),)),                # empty
                     (tools_config, ("read",)),            # not a list
                     (tools_config, ([1, 2],))):
        try:
            bad_call[0](*bad_call[1])
        except HerdrError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")

    # --- stop plans ---------------------------------------------------------
    sp = stop_plan("webapp", pid=4242, grace=5)
    assert sp["steps"][0] == {"signal": "SIGTERM", "delay": 0,
                              "argv": ["kill", "-TERM", "4242"]}
    assert sp["steps"][1] == {"signal": "SIGKILL", "delay": 5,
                              "argv": ["kill", "-KILL", "4242"]}
    assert stop_plan("webapp") == stop_plan("webapp")   # deterministic
    mux = stop_plan("webapp", pid=None, mux="tmux")
    assert mux["steps"][0]["argv"] == ["tmux", "kill-session", "-t", "webapp"]
    zed = stop_plan("webapp", pid=None, mux="zellij")
    assert zed["steps"][0]["argv"] == ["zellij", "delete-session", "webapp"]
    for bad_call in ((stop_plan, ("webapp", 0)),
                     (stop_plan, ("webapp", -1)),
                     (stop_plan, ("webapp", "4242")),
                     (stop_plan, ("webapp", 4242, 999)),    # grace too big
                     (stop_plan, ("webapp", 4242, -1)),
                     (stop_plan, ("../x", 4242)),
                     (stop_plan, ("webapp", None, 5, "screen"))):
        try:
            bad_call[0](*bad_call[1])
        except HerdrError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")

    # --- session state round-trip through a file (tempfile only) ------------
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sessions.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(STATE)
        with open(path, "r", encoding="utf-8") as fh:
            again = parse_sessions(fh.read())
        assert summarize(again) == counts


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
