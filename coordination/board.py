#!/usr/bin/env python3
"""RetroBake shared agent board - the central database every agent reads and writes.

All agents coordinate through coordination/retrobake.db (SQLite, stdlib only).

Usage:
  python3 coordination/board.py init
  python3 coordination/board.py status                      # overview of everything
  python3 coordination/board.py tasks [--agent NAME] [--state todo|doing|blocked|done]
  python3 coordination/board.py add-task AGENT "title" ["details"] [--depends ID,ID]
  python3 coordination/board.py claim ID AGENT
  python3 coordination/board.py set-state ID todo|doing|blocked|done ["note"]
  python3 coordination/board.py decide AGENT "topic" "decision"     # record a design decision
  python3 coordination/board.py decisions [topic]
  python3 coordination/board.py note AGENT "message" [--to AGENT]    # hand-off / message
  python3 coordination/board.py inbox AGENT
  python3 coordination/board.py contract AGENT "name" "path/or/spec" # publish an interface others build on
  python3 coordination/board.py contracts
  python3 coordination/board.py export                       # write readable BOARD.md snapshot
"""
import sqlite3, sys, os, datetime

def _db_path():
    """One shared DB for every agent, even ones running in separate git worktrees."""
    if os.environ.get("RETROBAKE_BOARD"):
        return os.environ["RETROBAKE_BOARD"]
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        import subprocess
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=here, capture_output=True, text=True, check=True).stdout.strip()
        return os.path.join(os.path.dirname(common), "coordination", "retrobake.db")
    except Exception:
        return os.path.join(here, "retrobake.db")

DB = _db_path()
STATES = ("todo", "doing", "blocked", "done")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, agent TEXT NOT NULL, title TEXT NOT NULL, details TEXT DEFAULT '',
  state TEXT NOT NULL DEFAULT 'todo', depends TEXT DEFAULT '', note TEXT DEFAULT '',
  created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY, agent TEXT, topic TEXT, decision TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY, from_agent TEXT, to_agent TEXT DEFAULT '*', message TEXT,
  created TEXT, read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contracts(
  id INTEGER PRIMARY KEY, agent TEXT, name TEXT UNIQUE, spec TEXT, updated TEXT);
"""

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con

def opt(args, flag):
    if flag in args:
        i = args.index(flag)
        val = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
        return val
    return None

def show(rows, cols):
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    if not rows:
        print("(none)")

def main(argv):
    if not argv:
        print(__doc__); return 1
    cmd, args = argv[0], argv[1:]
    con = db()
    if cmd == "init":
        print(f"Board ready at {DB}")
    elif cmd == "export":
        out = os.path.join(os.path.dirname(DB), "BOARD.md")
        lines = ["# RetroBake agent board (snapshot)", "", "## Tasks", "| id | agent | state | title | note |", "|---|---|---|---|---|"]
        for r in con.execute("SELECT * FROM tasks ORDER BY id"):
            lines.append(f"| {r['id']} | {r['agent']} | {r['state']} | {r['title']} | {r['note']} |")
        lines += ["", "## Decisions", "| topic | decision | by |", "|---|---|---|"]
        for r in con.execute("SELECT * FROM decisions ORDER BY id"):
            lines.append(f"| {r['topic']} | {r['decision']} | {r['agent']} |")
        lines += ["", "## Contracts", "| name | owner | spec |", "|---|---|---|"]
        for r in con.execute("SELECT * FROM contracts ORDER BY name"):
            lines.append(f"| {r['name']} | {r['agent']} | {r['spec']} |")
        open(out, "w").write("\n".join(lines) + "\n")
        print(f"exported {out}")
    elif cmd == "status":
        print("== Tasks by state ==")
        for s in STATES:
            n = con.execute("SELECT COUNT(*) FROM tasks WHERE state=?", (s,)).fetchone()[0]
            print(f"  {s}: {n}")
        print("== Open tasks ==")
        show(con.execute("SELECT id,agent,state,title FROM tasks WHERE state!='done' ORDER BY id").fetchall(),
             ("id", "agent", "state", "title"))
        print("== Latest decisions ==")
        show(con.execute("SELECT topic,decision,agent FROM decisions ORDER BY id DESC LIMIT 10").fetchall(),
             ("topic", "decision", "agent"))
        print("== Contracts ==")
        show(con.execute("SELECT name,agent,spec FROM contracts ORDER BY name").fetchall(), ("name", "agent", "spec"))
    elif cmd == "tasks":
        agent, state = opt(args, "--agent"), opt(args, "--state")
        q, p = "SELECT * FROM tasks WHERE 1=1", []
        if agent: q += " AND agent=?"; p.append(agent)
        if state: q += " AND state=?"; p.append(state)
        show(con.execute(q + " ORDER BY id", p).fetchall(), ("id", "agent", "state", "title", "depends", "note"))
    elif cmd == "add-task":
        dep = opt(args, "--depends") or ""
        agent, title = args[0], args[1]
        details = args[2] if len(args) > 2 else ""
        cur = con.execute("INSERT INTO tasks(agent,title,details,depends,created,updated) VALUES(?,?,?,?,?,?)",
                          (agent, title, details, dep, now(), now()))
        print(f"task {cur.lastrowid} -> {agent}")
    elif cmd == "claim":
        con.execute("UPDATE tasks SET agent=?, state='doing', updated=? WHERE id=?", (args[1], now(), int(args[0])))
        print(f"task {args[0]} claimed by {args[1]}")
    elif cmd == "set-state":
        if args[1] not in STATES:
            print(f"state must be one of {STATES}"); return 1
        note = args[2] if len(args) > 2 else ""
        con.execute("UPDATE tasks SET state=?, note=?, updated=? WHERE id=?", (args[1], note, now(), int(args[0])))
        print(f"task {args[0]} -> {args[1]}")
    elif cmd == "decide":
        con.execute("INSERT INTO decisions(agent,topic,decision,created) VALUES(?,?,?,?)", (args[0], args[1], args[2], now()))
        print("decision recorded")
    elif cmd == "decisions":
        if args:
            rows = con.execute("SELECT * FROM decisions WHERE topic LIKE ? ORDER BY id", (f"%{args[0]}%",)).fetchall()
        else:
            rows = con.execute("SELECT * FROM decisions ORDER BY id").fetchall()
        show(rows, ("id", "topic", "decision", "agent", "created"))
    elif cmd == "note":
        to = opt(args, "--to") or "*"
        frm = opt(args, "--from")
        pos, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a in ("--to", "--from"):
                skip = True
            else:
                pos.append(a)
        if frm:
            pos.insert(0, frm)
        if len(pos) < 2:
            sys.exit('usage: note AGENT "message" [--to AGENT]  (or --from AGENT)')
        con.execute("INSERT INTO notes(from_agent,to_agent,message,created) VALUES(?,?,?,?)", (pos[0], to, pos[1], now()))
        print(f"note sent to {to}")
    elif cmd == "inbox":
        rows = con.execute("SELECT * FROM notes WHERE (to_agent=? OR to_agent='*') AND read=0 ORDER BY id", (args[0],)).fetchall()
        show(rows, ("id", "from_agent", "to_agent", "message", "created"))
        con.execute("UPDATE notes SET read=1 WHERE to_agent=? AND read=0", (args[0],))
    elif cmd == "contract":
        con.execute("INSERT INTO contracts(agent,name,spec,updated) VALUES(?,?,?,?) "
                    "ON CONFLICT(name) DO UPDATE SET agent=excluded.agent, spec=excluded.spec, updated=excluded.updated",
                    (args[0], args[1], args[2], now()))
        print(f"contract '{args[1]}' published")
    elif cmd == "contracts":
        show(con.execute("SELECT * FROM contracts ORDER BY name").fetchall(), ("name", "agent", "spec", "updated"))
    else:
        print(__doc__); return 1
    con.commit()
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
