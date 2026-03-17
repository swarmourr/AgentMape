#!/usr/bin/env python3.11
"""
AgentMape MAPE-K — Restart & Monitoring Console

Usage:
  python3.11 restart_system.py              # stop, restart all services, then show console
  python3.11 restart_system.py --console    # skip restart, attach console to running services
  python3.11 restart_system.py -c           # same as --console

Keyboard shortcuts (in console):
  q / Q        → quit console (services keep running)
  r / R        → force re-check health & connectivity now
  Ctrl-C       → stop ALL services and exit
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

try:
    from rich import box
    from rich.align import Align
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

HEALTH_INTERVAL   = 5    # seconds between background health polls
LOG_POLL_INTERVAL = 0.3  # seconds between log file reads
REFRESH_HZ        = 2    # live console refreshes per second
MAX_LOG_LINES     = 300  # lines kept per service
ALL_LOG_KEEP      = 600  # interleaved log buffer size

SVC_COLORS = {
    "Monitor":          "cyan",
    "Analyzer":         "green",
    "Planner":          "yellow",
    "Evaluator":        "red",
    "Pegasus Provider": "magenta",
}

# ── LLM log patterns ──────────────────────────────────────────────────────────
# Each entry: (service_name, regex, event_type)
#   event_type: "request" | "success" | "error"
LLM_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Planner — OpenAI call start
    ("Planner",   re.compile(r"\[OpenAI\] Calling model\s+([\w.\-]+)"),                       "request"),
    # Planner — OpenAI response received
    ("Planner",   re.compile(r"OpenAI response length:"),                                      "success"),
    # Planner — per-model plan parsed ok
    ("Planner",   re.compile(r"Model\s+(openai/[\w.\-]+|ollama/[\w.\-]+)\s+plan parsed"),     "success"),
    # Planner — model returned nothing
    ("Planner",   re.compile(r"Model\s+(openai/[\w.\-]+|ollama/[\w.\-]+)\s+returned no resp"),"error"),
    # Planner — Ollama call
    ("Planner",   re.compile(r"Calling Ollama with prompt"),                                   "request"),
    # Planner — Ollama response
    ("Planner",   re.compile(r"Ollama response length:"),                                      "success"),
    # Analyzer — OpenAI call
    ("Analyzer",  re.compile(r"Calling OpenAI|call_openai|openai.*glm|glm.*openai"),          "request"),
    # Analyzer — OpenAI success
    ("Analyzer",  re.compile(r"LLM analysis.*success|openai.*response|analysis.*completed"),  "success"),
    # Evaluator — council member called
    ("Evaluator", re.compile(r"Running council with \d+ member"),                             "request"),
    # Evaluator — member result
    ("Evaluator", re.compile(r"(✓|✗)\s+(openai/[\w.\-]+|[\w.\-]+):\s+confidence="),          "success"),
    # Evaluator — member error
    ("Evaluator", re.compile(r"Council member\s+([\w./\-]+)\s+(?:thread error|failed)"),      "error"),
]

# ─────────────────────────────────────────────────────────────────────────────
# LLM TRACKER
# ─────────────────────────────────────────────────────────────────────────────
class ModelStat:
    __slots__ = ("requests", "successes", "errors", "last_seen", "last_ms")

    def __init__(self) -> None:
        self.requests  = 0
        self.successes = 0
        self.errors    = 0
        self.last_seen = "—"
        self.last_ms: int | None = None


class LLMTracker:
    """
    Parses log lines for LLM request/response events.
    Maintains per-(service, model) counters.
    """
    def __init__(self) -> None:
        # key: (service, model_label) → ModelStat
        self._stats: dict[tuple[str, str], ModelStat] = {}
        self._lock = threading.Lock()

        # Pending request label per service (last "Calling model X" seen)
        self._pending: dict[str, str] = {}

    def ingest(self, service: str, line: str) -> None:
        for svc_filter, pattern, event in LLM_PATTERNS:
            if svc_filter != service:
                continue
            m = pattern.search(line)
            if m is None:
                continue

            # Try to extract model name from capture group
            model_label = m.group(1) if m.lastindex and m.lastindex >= 1 else None

            # For "Calling model X" pattern, store as pending for this service
            if event == "request" and model_label:
                self._pending[service] = model_label
                key = (service, model_label)
            elif event == "request" and not model_label:
                # Generic request (e.g. Ollama call without model name)
                model_label = self._pending.get(service, "unknown")
                key = (service, model_label)
            elif event in ("success", "error"):
                if model_label:
                    key = (service, model_label)
                else:
                    model_label = self._pending.get(service, "unknown")
                    key = (service, model_label)
            else:
                continue

            with self._lock:
                if key not in self._stats:
                    self._stats[key] = ModelStat()
                stat = self._stats[key]

                if event == "request":
                    stat.requests += 1
                elif event == "success":
                    stat.successes += 1
                elif event == "error":
                    stat.errors += 1

                stat.last_seen = datetime.now().strftime("%H:%M:%S")
            break  # first matching pattern per line

    def snapshot(self) -> list[tuple[str, str, ModelStat]]:
        """Return sorted list of (service, model, stat) — most recent first."""
        with self._lock:
            items = [(svc, mdl, st) for (svc, mdl), st in self._stats.items()]
        items.sort(key=lambda x: x[2].last_seen, reverse=True)
        return items


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE STATE
# ─────────────────────────────────────────────────────────────────────────────
class ServiceState:
    def __init__(self, name: str, port: int, log_stem: str):
        self.name      = name
        self.port      = port
        self.log_path  = LOG_DIR / f"{log_stem}.log"
        self.pid_path  = LOG_DIR / f"{log_stem}.pid"

        self.pid: int | None         = None
        self.status: str             = "pending"
        self.response_ms: int | None = None
        self.detail: str             = ""
        self.last_check: str         = "—"

        self.logs: deque[str]        = deque(maxlen=MAX_LOG_LINES)
        self._log_pos: int           = 0
        self._lock                   = threading.Lock()

    def poll_logs(self) -> list[str]:
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
            # Try to read PID from pid file if not set
            if self.pid is None and self.pid_path.exists():
                try:
                    self.pid = int(self.pid_path.read_text().strip())
                except Exception:
                    pass
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
                strat     = data["aggregation_strategy"]
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

all_logs: deque[tuple[str, str, str]] = deque(maxlen=ALL_LOG_KEEP)
all_logs_lock = threading.Lock()

llm_tracker = LLMTracker()

start_time: datetime = datetime.now()
_stop_event  = threading.Event()
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
                        llm_tracker.ingest(st.name, line)
        time.sleep(LOG_POLL_INTERVAL)


# ─────────────────────────────────────────────────────────────────────────────
# RICH RENDERERS
# ─────────────────────────────────────────────────────────────────────────────
def _overall_status() -> tuple[str, str]:
    all_up    = all(s.status == "up" for s in svc_states.values())
    all_conn  = all(c.ok is not False for c in conn_states)
    down_svcs = [s.name for s in svc_states.values() if s.status == "down"]

    if all_up and all_conn:
        return "● ALL SYSTEMS OPERATIONAL", "bold green"
    if all_up and not all_conn:
        return "● SERVICES UP  /  CONNECTIVITY ISSUES", "bold yellow"
    if down_svcs:
        return f"● DEGRADED  —  DOWN: {', '.join(down_svcs)}", "bold red"
    return "● STARTING UP…", "bold yellow"


def render_header() -> Panel:
    elapsed = datetime.now() - start_time
    h, rem  = divmod(int(elapsed.total_seconds()), 3600)
    m, s    = divmod(rem, 60)
    uptime  = f"{h:02d}:{m:02d}:{s:02d}"
    now     = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    lbl, sty = _overall_status()

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
                 border_style="cyan", padding=(0, 1))


def render_service_table() -> Panel:
    t = Table(box=box.SIMPLE_HEAD, expand=True,
              header_style="bold cyan", border_style="dim",
              show_edge=False, pad_edge=False)
    t.add_column("Service",  style="bold", min_width=18)
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
            name, str(st.port), dot,
            str(st.pid) if st.pid else "—",
            rt, st.last_check, st.detail or "—",
        )

    return Panel(t, title="[bold]Service Health[/]", border_style="blue", padding=(0, 1))


def render_conn_table() -> Panel:
    t = Table(box=box.SIMPLE_HEAD, expand=True,
              header_style="bold cyan", border_style="dim",
              show_edge=False, pad_edge=False)
    t.add_column("From",   style="bold", min_width=14)
    t.add_column("",       width=3, justify="center")
    t.add_column("To",     min_width=14)
    t.add_column("Result", min_width=16)

    for cs in conn_states:
        if cs.ok is True:
            arrow  = Text("→", style="green")
            result = Text(f"✔  {cs.ms}ms" if cs.ms else "✔  filesystem", style="green")
        elif cs.ok is False:
            arrow  = Text("→", style="red")
            result = Text("✘  unreachable", style="bold red")
        else:
            arrow  = Text("→", style="dim")
            result = Text("checking…", style="dim yellow")
        t.add_row(cs.frm, arrow, cs.to, result)

    ok_n   = sum(1 for c in conn_states if c.ok is True)
    fail_n = sum(1 for c in conn_states if c.ok is False)
    total  = len(conn_states)
    if fail_n == 0 and ok_n == total:
        summary = Text(f"  All {total} OK", style="bold green")
    else:
        summary = Text(f"  {ok_n}/{total} OK  —  {fail_n} failed", style="bold yellow")
    t.add_row("", Text(""), Text(""), Text(""))
    t.add_row("", Text(""), summary, Text(""))

    return Panel(t, title="[bold]Inter-Service Connectivity[/]", border_style="blue", padding=(0, 1))


def render_llm_panel() -> Panel:
    t = Table(box=box.SIMPLE_HEAD, expand=True,
              header_style="bold magenta", border_style="dim",
              show_edge=False, pad_edge=False)
    t.add_column("Service",   style="bold", width=12)
    t.add_column("Model",     min_width=20)
    t.add_column("Reqs",      justify="right", width=6)
    t.add_column("OK",        justify="right", width=6)
    t.add_column("Err",       justify="right", width=6)
    t.add_column("Rate",      justify="right", width=7)
    t.add_column("Last seen", width=10)

    rows = llm_tracker.snapshot()

    if not rows:
        t.add_row(
            Text("—", style="dim"), Text("waiting for LLM activity…", style="dim"),
            "—", "—", "—", "—", "—",
        )
    else:
        for svc, model, stat in rows:
            color = SVC_COLORS.get(svc, "white")
            reqs  = stat.requests
            ok    = stat.successes
            err   = stat.errors

            # Success rate based on completed (ok + err)
            completed = ok + err
            rate_str  = f"{ok/completed*100:.0f}%" if completed > 0 else "—"
            rate_sty  = "green" if completed > 0 and ok / completed >= 0.8 else "yellow" if completed > 0 else "dim"

            err_sty   = "red" if err > 0 else "dim"

            t.add_row(
                Text(svc, style=f"bold {color}"),
                Text(model, style="bold"),
                str(reqs),
                Text(str(ok),  style="green"),
                Text(str(err), style=err_sty),
                Text(rate_str, style=rate_sty),
                Text(stat.last_seen, style="dim"),
            )

    # Totals footer
    if rows:
        total_reqs = sum(s.requests  for _, _, s in rows)
        total_ok   = sum(s.successes for _, _, s in rows)
        total_err  = sum(s.errors    for _, _, s in rows)
        completed  = total_ok + total_err
        rate_str   = f"{total_ok/completed*100:.0f}%" if completed > 0 else "—"
        t.add_row("", Text(""), Text(""), Text(""), Text(""), Text(""), Text(""))
        t.add_row(
            Text("TOTAL", style="bold dim"),
            Text(f"{len(rows)} model(s)", style="dim"),
            Text(str(total_reqs), style="bold"),
            Text(str(total_ok),  style="bold green"),
            Text(str(total_err), style="bold red" if total_err else "dim"),
            Text(rate_str, style="bold"),
            Text(""),
        )

    return Panel(t, title="[bold magenta]LLM Model Activity[/]", border_style="magenta", padding=(0, 1))


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
        border_style="blue", padding=(0, 1),
    )


def render_footer() -> Text:
    t = Text(justify="center", style="dim")
    t.append(" q", style="bold yellow");      t.append(": quit (services keep running)   ")
    t.append("r",  style="bold yellow");      t.append(": force re-check   ")
    t.append("Ctrl-C", style="bold yellow");  t.append(": stop ALL services ")
    return t


def build_layout(console_height: int) -> Layout:
    # header=3  top=16  llm=9  logs=rest  footer=1
    llm_height = 9
    top_height  = 16
    log_height  = max(console_height - 3 - top_height - llm_height - 1, 5)

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top",    size=top_height),
        Layout(name="llm",    size=llm_height),
        Layout(name="logs",   size=log_height),
        Layout(name="footer", size=1),
    )
    layout["top"].split_row(
        Layout(name="services",     ratio=3),
        Layout(name="connections",  ratio=2),
    )
    layout["header"].update(render_header())
    layout["services"].update(render_service_table())
    layout["connections"].update(render_conn_table())
    layout["llm"].update(render_llm_panel())
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
            [PYTHON, script], cwd=work_dir, env=env,
            stdout=log_fh, stderr=subprocess.STDOUT,
        )
        log_fh.close()

        pid_path.write_text(str(proc.pid))
        svc_states[name].pid    = proc.pid
        svc_states[name].status = "starting"
        console.print(f"  [bold]{name}[/]  PID [cyan]{proc.pid}[/]  log → {log_path.name}")

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


def attach_console_only(console: Console) -> None:
    """Read existing PID files and do a health check without restarting."""
    console.print("[cyan]  Console-only mode — attaching to running services…[/]")
    for name, _, _, port, log_stem, _ in SERVICES:
        pid_path = LOG_DIR / f"{log_stem}.pid"
        if pid_path.exists():
            try:
                svc_states[name].pid = int(pid_path.read_text().strip())
            except Exception:
                pass
        # Seek to end of existing log file so we only show new lines
        log_path = LOG_DIR / f"{log_stem}.log"
        if log_path.exists():
            try:
                svc_states[name]._log_pos = log_path.stat().st_size
            except Exception:
                pass
        svc_states[name].check_health()
        status = svc_states[name].status
        color  = "green" if status == "up" else "red"
        console.print(f"  [bold]{name:20}[/]  [{color}]{status.upper()}[/]"
                      f"  PID {svc_states[name].pid or '—'}")
    console.print("")


# ─────────────────────────────────────────────────────────────────────────────
# KEYBOARD HANDLER
# ─────────────────────────────────────────────────────────────────────────────
class RawKeyboard:
    def __init__(self) -> None:
        self._fd: int | None = None
        self._old_settings   = None
        self._stop = threading.Event()
        self.quit   = threading.Event()
        self.recheck = threading.Event()

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        try:
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            threading.Thread(target=self._run, daemon=True).start()
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
    console_only = "--console" in sys.argv or "-c" in sys.argv
    console      = Console()

    console.print()
    console.rule("[bold cyan]AgentMape MAPE-K — Restart & Monitor[/]")
    console.print()

    if console_only:
        # ── Attach-only mode ─────────────────────────────────────────────────
        attach_console_only(console)
        start_time = datetime.now()
    else:
        # ── Full restart ──────────────────────────────────────────────────────
        stop_all(console)
        console.print()
        start_time = datetime.now()
        start_all(console)

    # ── Initial connectivity check ────────────────────────────────────────────
    console.print("[cyan]Running connectivity checks…[/]")
    for cs in conn_states:
        cs.check()
    for st in svc_states.values():
        st.check_health()
    ok_n = sum(1 for c in conn_states if c.ok)
    console.print(f"[green]Done.  {ok_n}/{len(conn_states)} connections verified.[/]")
    console.print()
    time.sleep(0.5)

    # ── Background threads ────────────────────────────────────────────────────
    threading.Thread(target=_health_loop,   daemon=True, name="health").start()
    threading.Thread(target=_log_poll_loop, daemon=True, name="log-poll").start()

    # ── Live console ──────────────────────────────────────────────────────────
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
        console.print()
        stop_all(console)
        sys.exit(0)

    finally:
        _stop_event.set()
        kb.stop()

    console.print()
    console.print("[green]Monitoring console closed.  Services are still running.[/]")
    console.print(f"  Logs : {LOG_DIR}")
    console.print(f"  Stop : ./stop_system.sh")
    console.print()


if __name__ == "__main__":
    main()
