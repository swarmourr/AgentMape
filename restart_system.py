#!/usr/bin/env python3.11
"""
AgentMape MAPE-K — Restart & Monitoring Console
Stops all services, starts them in order, then shows a live TUI dashboard.

  q / Q        → quit console (services keep running)
  r / R        → force re-check all health & connectivity
  Ctrl-C       → stop ALL services and exit
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "rich"], check=True)
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_DIR    = SCRIPT_DIR / "logs"
PIPE_DIR   = SCRIPT_DIR / "pipeline_data"
PYTHON     = "python3.11"

SERVICES: list[tuple] = [
    # (display_name, subdir, script, port, log_stem, env_overrides)
    ("Monitor",          "Monitoring",      "server_rest.py",              8080, "monitor",   {}),
    ("Pegasus Provider", "PegasusProvider", "pegasus_provider_service.py", 8085, "provider",  {"PEGASUS_PROVIDER_PORT": "8085"}),
    ("Analyzer",         "Analyzer",        "analyzer_rest.py",            8081, "analyzer",  {}),
    ("Planner",          "Planner",         "planner_rest.py",             8082, "planner",   {}),
    ("Evaluator",        "Evaluator",       "evaluator_rest.py",           8084, "evaluator", {}),
]

CONNECTIONS: list[tuple] = [
    # (from_label, to_label, url_or_None_for_filesystem)
    ("Monitor",          "Analyzer",       "http://localhost:8081/health"),
    ("Monitor",          "Planner",        "http://localhost:8082/health"),
    ("Analyzer",         "Monitor",        "http://localhost:8080/health"),
    ("Planner",          "Monitor",        "http://localhost:8080/health"),
    ("Planner",          "Analyzer",       "http://localhost:8081/health"),
    ("Evaluator",        "Pipeline dir",   None),
    ("Pegasus Provider", "Monitor",        "http://localhost:8080/health"),
    ("All agents",       "LLM endpoint",   "https://ellm.nrp-nautilus.io/v1/models"),
]

LLM_API_KEY      = "XUCcJ4cCRL3bUj9qCZKvMmbY5nGDye4P"
PIPELINE_PENDING = PIPE_DIR / "planner_output" / "pending"

HEALTH_INTERVAL  = 5     # seconds between background health polls
LOG_POLL_INTERVAL = 0.3  # seconds between log file reads
REFRESH_HZ       = 2     # live console refreshes per second
MAX_LOG_LINES    = 300   # lines kept per service
ALL_LOG_KEEP     = 600   # interleaved log buffer size

SVC_COLORS = {
    "Monitor":          "cyan",
    "Analyzer":         "green",
    "Planner":          "yellow",
    "Evaluator":        "red",
    "Pegasus Provider": "magenta",
}

# ─────────────────────────────────────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────────────────────────────────────
class ServiceState:
    def __init__(self, name: str, port: int, log_stem: str):
        self.name      = name
        self.port      = port
        self.log_path  = LOG_DIR / f"{log_stem}.log"
        self.pid_path  = LOG_DIR / f"{log_stem}.pid"

        self.pid: int | None        = None
        self.status: str            = "pending"   # pending | starting | up | down
        self.response_ms: int | None = None
        self.detail: str            = ""
        self.last_check: str        = "—"

        self.logs: deque[str]       = deque(maxlen=MAX_LOG_LINES)
        self._log_pos: int          = 0
        self._lock                  = threading.Lock()

    def poll_logs(self) -> list[str]:
        """Read new lines from the log file since last poll. Returns new lines."""
        new: list[str] = []
        try:
            with open(self.log_path, "r", errors="replace") as f:
                f.seek(self._log_pos)
                chunk = f.read()
                self._log_pos = f.tell()
            for line in chunk.splitlines():
                stripped = line.strip()
                if stripped:
                    with self._lock:
                        self.logs.append(stripped)
                    new.append(stripped)
        except OSError:
            pass
        return new

    def check_health(self) -> None:
        url = f"http://localhost:{self.port}/health"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=3) as resp:
                elapsed = int((time.monotonic() - t0) * 1000)
                body = resp.read().decode(errors="replace")
            self.status      = "up"
            self.response_ms = elapsed
            self.last_check  = datetime.now().strftime("%H:%M:%S")
            self._parse_detail(body)
        except Exception:
            self.status      = "down"
            self.response_ms = None
            self.last_check  = datetime.now().strftime("%H:%M:%S")
            self.detail      = "no response"

    def _parse_detail(self, body: str) -> None:
        try:
            data = json.loads(body)
            if "llm_backend" in data:
                lb = data["llm_backend"]
                self.detail = f"{lb.get('provider','?')} / {lb.get('model','?')}"
            elif "aggregation_strategy" in data:
                strat = data["aggregation_strategy"]
                threshold = data.get("quality_gate_threshold", "")
                self.detail = f"{strat}  gate={threshold}"
            elif "openai_enabled" in data:
                self.detail = "openai ✔" if data["openai_enabled"] else "openai ✗"
            elif "service" in data:
                self.detail = data["service"]
            elif "agent_id" in data:
                self.detail = data["agent_id"]
            else:
                self.detail = data.get("status", "ok")
        except Exception:
            self.detail = "ok"


class ConnState:
    def __init__(self, frm: str, to: str, url: str | None):
        self.frm    = frm
        self.to     = to
        self.url    = url
        self.ok: bool | None = None
        self.ms: int | None  = None

    def check(self) -> None:
        if self.url is None:
            self.ok = PIPELINE_PENDING.is_dir()
            self.ms = None
            return
        try:
            headers: dict[str, str] = {}
            if "ellm" in self.url:
                headers["Authorization"] = f"Bearer {LLM_API_KEY}"
            req = urllib.request.Request(self.url, headers=headers)
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.ms = int((time.monotonic() - t0) * 1000)
                self.ok = resp.status < 400
        except Exception:
            self.ok = False
            self.ms = None


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────
svc_states: dict[str, ServiceState] = {
    name: ServiceState(name, port, log_stem)
    for name, _, _, port, log_stem, _ in SERVICES
}
conn_states: list[ConnState] = [
    ConnState(frm, to, url) for frm, to, url in CONNECTIONS
]

all_logs: deque[tuple[str, str, str]] = deque(maxlen=ALL_LOG_KEEP)  # (svc, line, color)
all_logs_lock = threading.Lock()

start_time: datetime = datetime.now()
_stop_event = threading.Event()
_force_check = threading.Event()


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND THREADS
# ─────────────────────────────────────────────────────────────────────────────
def _health_loop() -> None:
    while not _stop_event.is_set():
        for st in svc_states.values():
            st.check_health()
        for cs in conn_states:
            cs.check()
        # Wait, but wake up immediately if forced
        _force_check.clear()
        _force_check.wait(timeout=HEALTH_INTERVAL)


def _log_poll_loop() -> None:
    while not _stop_event.is_set():
        for st in svc_states.values():
            new_lines = st.poll_logs()
            if new_lines:
                color = SVC_COLORS.get(st.name, "white")
                with all_logs_lock:
                    for line in new_lines:
                        all_logs.append((st.name, line, color))
        time.sleep(LOG_POLL_INTERVAL)


# ─────────────────────────────────────────────────────────────────────────────
# RICH RENDERERS
# ─────────────────────────────────────────────────────────────────────────────
def _overall_status() -> tuple[str, str]:
    """Return (label, style)."""
    all_up   = all(s.status == "up"   for s in svc_states.values())
    all_conn = all(c.ok is not False   for c in conn_states)
    down_svcs = [s.name for s in svc_states.values() if s.status == "down"]

    if all_up and all_conn:
        return "● ALL SYSTEMS OPERATIONAL", "bold green"
    if all_up and not all_conn:
        return "● SERVICES UP  /  CONNECTIVITY ISSUES", "bold yellow"
    if down_svcs:
        names = ", ".join(down_svcs)
        return f"● DEGRADED  —  DOWN: {names}", "bold red"
    return "● STARTING UP…", "bold yellow"


def render_header() -> Panel:
    elapsed   = datetime.now() - start_time
    h, rem    = divmod(int(elapsed.total_seconds()), 3600)
    m, s      = divmod(rem, 60)
    uptime    = f"{h:02d}:{m:02d}:{s:02d}"
    now       = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    lbl, sty  = _overall_status()

    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    grid.add_row(
        Text(f"  {now}", style="dim"),
        Text(lbl, style=sty),
        Text(f"uptime {uptime}  ", style="dim"),
    )
    return Panel(grid,
                 title="[bold cyan]AgentMape MAPE-K — Monitoring Console[/]",
                 border_style="cyan",
                 padding=(0, 1))


def render_service_table() -> Panel:
    t = Table(box=box.SIMPLE_HEAD, expand=True,
              header_style="bold cyan", border_style="dim",
              show_edge=False, pad_edge=False)
    t.add_column("Service",  style="bold",   min_width=18)
    t.add_column("Port",     justify="right", width=6)
    t.add_column("Status",   width=9)
    t.add_column("PID",      justify="right", width=7)
    t.add_column("RT",       justify="right", width=7)
    t.add_column("Checked",  width=10)
    t.add_column("Detail",   style="dim")

    for name, *_ in SERVICES:
        st = svc_states[name]
        if st.status == "up":
            dot = Text("● UP",   style="bold green")
            rt  = f"{st.response_ms}ms" if st.response_ms else "—"
        elif st.status == "down":
            dot = Text("● DOWN", style="bold red")
            rt  = "—"
        elif st.status == "starting":
            dot = Text("◌ …",   style="bold yellow")
            rt  = "—"
        else:
            dot = Text("○ —",   style="dim")
            rt  = "—"

        t.add_row(
            name,
            str(st.port),
            dot,
            str(st.pid) if st.pid else "—",
            rt,
            st.last_check,
            st.detail or "—",
        )

    return Panel(t, title="[bold]Service Health[/]", border_style="blue", padding=(0, 1))


def render_conn_table() -> Panel:
    t = Table(box=box.SIMPLE_HEAD, expand=True,
              header_style="bold cyan", border_style="dim",
              show_edge=False, pad_edge=False)
    t.add_column("From",   style="bold", min_width=16)
    t.add_column("",       width=3, justify="center")
    t.add_column("To",     min_width=14)
    t.add_column("Result", min_width=18)

    for cs in conn_states:
        if cs.ok is True:
            arrow  = Text("→", style="green")
            result = Text(
                f"✔  {cs.ms}ms" if cs.ms else "✔  filesystem",
                style="green",
            )
        elif cs.ok is False:
            arrow  = Text("→", style="red")
            result = Text("✘  unreachable", style="bold red")
        else:
            arrow  = Text("→", style="dim")
            result = Text("checking…", style="dim yellow")

        t.add_row(cs.frm, arrow, cs.to, result)

    # Summary line
    ok_count   = sum(1 for c in conn_states if c.ok is True)
    fail_count = sum(1 for c in conn_states if c.ok is False)
    total      = len(conn_states)
    if fail_count == 0 and ok_count == total:
        summary = Text(f"  All {total} connections OK", style="bold green")
    else:
        summary = Text(f"  {ok_count}/{total} OK  —  {fail_count} failed", style="bold yellow")

    t.add_row("", Text(""), Text(""), Text(""))
    t.add_row("", Text(""), summary, Text(""))

    return Panel(t, title="[bold]Inter-Service Connectivity[/]", border_style="blue", padding=(0, 1))


def render_logs(visible_lines: int) -> Panel:
    with all_logs_lock:
        recent = list(all_logs)[-(max(visible_lines, 4)):]

    text = Text(overflow="fold")
    for svc_name, line, color in recent:
        label = f"[{svc_name[:9]:<9}]"
        text.append(label + "  ", style=f"bold {color}")
        text.append(line + "\n",  style="white")

    return Panel(
        text,
        title=f"[bold]Live Logs[/]  [dim]({len(recent)} lines)[/]",
        border_style="blue",
        padding=(0, 1),
    )


def render_footer() -> Text:
    t = Text(justify="center", style="dim")
    t.append(" q", style="bold yellow"); t.append(": quit console (services keep running)   ")
    t.append("r", style="bold yellow"); t.append(": force re-check   ")
    t.append("Ctrl-C", style="bold yellow"); t.append(": stop ALL services ")
    return t


def build_layout(console_height: int) -> Layout:
    # Fixed rows: header=3, middle=18, footer=1; logs fill the rest
    log_height = max(console_height - 3 - 18 - 1, 6)

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="middle", size=18),
        Layout(name="logs",   size=log_height),
        Layout(name="footer", size=1),
    )
    layout["middle"].split_row(
        Layout(name="services",      ratio=3),
        Layout(name="connections",   ratio=2),
    )
    layout["header"].update(render_header())
    layout["services"].update(render_service_table())
    layout["connections"].update(render_conn_table())
    layout["logs"].update(render_logs(log_height - 4))
    layout["footer"].update(Align(render_footer(), vertical="middle"))
    return layout


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def _kill_port(port: int) -> None:
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{port}"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        for pid_str in out.split():
            try:
                os.kill(int(pid_str), signal.SIGKILL)
            except (ValueError, ProcessLookupError):
                pass
    except subprocess.CalledProcessError:
        pass


def stop_all(console: Console | None = None) -> None:
    msg = lambda s: console.print(s) if console else print(s)
    msg("[bold red]  Stopping all services…[/]")

    for stem in ["monitor", "analyzer", "planner", "executor", "evaluator", "provider", "dashboard"]:
        pf = LOG_DIR / f"{stem}.pid"
        if pf.exists():
            try:
                pid = int(pf.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                msg(f"  [yellow]  SIGTERM → PID {pid} ({stem})[/]")
                pf.unlink(missing_ok=True)
            except (ValueError, ProcessLookupError, OSError):
                pf.unlink(missing_ok=True)

    for port in [8080, 8081, 8082, 8083, 8084, 8085, 5000]:
        _kill_port(port)

    time.sleep(1)
    msg("[green]  All services stopped.[/]")


def start_all(console: Console) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    PIPELINE_PENDING.mkdir(parents=True, exist_ok=True)
    (PIPE_DIR / "planner_output" / "processed").mkdir(parents=True, exist_ok=True)
    (PIPE_DIR / "evaluator_output").mkdir(parents=True, exist_ok=True)

    for name, subdir, script, port, log_stem, env_overrides in SERVICES:
        console.rule(f"[bold cyan]{name}[/]")
        log_path = LOG_DIR / f"{log_stem}.log"
        pid_path = LOG_DIR / f"{log_stem}.pid"
        work_dir = SCRIPT_DIR / subdir

        env = os.environ.copy()
        env.update(env_overrides)

        log_fh = open(log_path, "w")
        proc   = subprocess.Popen(
            [PYTHON, script],
            cwd=work_dir,
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
        log_fh.close()

        pid_path.write_text(str(proc.pid))
        svc_states[name].pid    = proc.pid
        svc_states[name].status = "starting"
        console.print(f"  [bold]{name}[/]  PID [cyan]{proc.pid}[/]  log → {log_path.name}")

        # Health gate
        console.print(f"  Waiting for :{port}", end="")
        for i in range(30):
            try:
                urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
                console.print(f"  [green]✔ up ({i+1}s)[/]")
                svc_states[name].status = "up"
                break
            except Exception:
                console.print(".", end="")
                time.sleep(1)
        else:
            console.print(f"  [red]✘ no response after 30s[/]")
            svc_states[name].status = "down"

        console.print("")


# ─────────────────────────────────────────────────────────────────────────────
# KEYBOARD HANDLER
# ─────────────────────────────────────────────────────────────────────────────
class RawKeyboard:
    """Non-blocking single-char reader in raw tty mode."""

    def __init__(self) -> None:
        self._fd: int | None       = None
        self._old_settings         = None
        self._thread: threading.Thread | None = None
        self._stop  = threading.Event()
        self.quit   = threading.Event()
        self.recheck = threading.Event()

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        try:
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self._old_settings and self._fd is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass

    def _run(self) -> None:
        import select
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.2)
                if r:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q"):
                        self.quit.set()
                    elif ch in ("r", "R"):
                        self.recheck.set()
                        _force_check.set()
            except Exception:
                break


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    global start_time
    console = Console()

    # ── Phase 1: Stop ────────────────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]AgentMape MAPE-K — Restart & Monitor[/]")
    console.print()
    stop_all(console)
    console.print()

    # ── Phase 2: Start ───────────────────────────────────────────────────────
    start_time = datetime.now()
    start_all(console)

    # ── Phase 3: Initial connectivity check ──────────────────────────────────
    console.print("[cyan]Running initial connectivity checks…[/]")
    for cs in conn_states:
        cs.check()
    for st in svc_states.values():
        st.check_health()
    ok_n = sum(1 for c in conn_states if c.ok)
    console.print(f"[green]Done.  {ok_n}/{len(conn_states)} connections verified.[/]")
    console.print()
    time.sleep(0.5)

    # ── Phase 4: Background threads ──────────────────────────────────────────
    ht = threading.Thread(target=_health_loop,   daemon=True, name="health")
    lt = threading.Thread(target=_log_poll_loop, daemon=True, name="log-poll")
    ht.start()
    lt.start()

    # ── Phase 5: Live console ────────────────────────────────────────────────
    kb = RawKeyboard()
    kb.start()

    console.print("[bold cyan]Entering monitoring console…[/]")
    time.sleep(0.4)

    try:
        with Live(
            build_layout(console.height),
            console=console,
            refresh_per_second=REFRESH_HZ,
            screen=True,
        ) as live:
            while True:
                if kb.quit.is_set():
                    break

                live.update(build_layout(console.height))
                time.sleep(1.0 / REFRESH_HZ)

    except KeyboardInterrupt:
        _stop_event.set()
        kb.stop()
        # Ctrl-C → stop all services
        console.print()
        stop_all(console)
        sys.exit(0)

    finally:
        _stop_event.set()
        kb.stop()

    # q was pressed — leave services running
    console.print()
    console.print("[green]Monitoring console closed.  Services are still running.[/]")
    console.print(f"  Logs  : {LOG_DIR}")
    console.print(f"  Stop  : ./stop_system.sh")
    console.print()


if __name__ == "__main__":
    main()
