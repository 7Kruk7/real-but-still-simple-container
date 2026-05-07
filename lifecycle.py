import argparse
import json
import os
import signal
import sys
import time
import uuid
import logging
from datetime import datetime
from argparse import Namespace

from container import (
    setup_bridge,
    setup_rootfs,
    setup_cgroups,
    run,
    cleanup,
    save_state,
    load_state,
    list_containers,
    parse_memory,
    STATE_DIR,
)

import linux

LOG_DIR = "/var/lib/minicontainer/logs"

def cmd_run(args):
    """Run a container in the background (daemonized)."""

    container_id = "mc-" + uuid.uuid4().hex[:8]
    memory_bytes = parse_memory(args.memory)
    command = [c for c in args.cmd if c != "--"]

    if not command:
        print("Error: no command specified")
        sys.exit(1)

    pid1 = os.fork()

    if pid1 > 0:
        os.waitpid(pid1, 0)
        print(f"{container_id}")
        return

    os.setsid()

    pid2 = os.fork()

    if pid2 > 0:
        os._exit(0)

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{container_id}.log")
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    os.close(log_fd)

    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    rootfs = None
    cgroup_path = None
    exit_code = None

    try:
        setup_bridge()
        rootfs = setup_rootfs(container_id, args.image)
        logging.info(f"Rootfs created at: {rootfs}")
        cgroup_path = setup_cgroups(container_id, memory_bytes, args.cpu)

        state = {
            "id": container_id,
            "state": "created",
            "pid": None,
            "image": args.image,
            "command": command,
            "memory": memory_bytes,
            "memory_raw": args.memory,
            "cpu": args.cpu,
            "timeout": args.timeout,
            "rootfs": rootfs,
            "cgroup_path": cgroup_path,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "stopped_at": None,
            "exit_code": None,
        }
        save_state(container_id, state)

        exit_code = run(rootfs, cgroup_path, command, args.timeout, container_id)

    except Exception as e:
        logging.error(f"Container {container_id} failed: {e}")
        exit_code = 1

    finally:
        try:
            existing = load_state(container_id)
            if existing:
                existing["state"] = "stopped"
                existing["stopped_at"] = datetime.now().isoformat()
                existing["exit_code"] = exit_code
                save_state(container_id, existing)
        except Exception as e:
            logging.error(f"Failed to update state: {e}")

        if rootfs or cgroup_path:
            cleanup(rootfs, cgroup_path, container_id)

    os._exit(exit_code if exit_code is not None else 1)


def is_pid_alive(pid):
    """Check if a process is still running using kill(pid, 0)."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process is alive, but we don't have a permisson to signal it
        return True


def format_uptime(started_at_str):
    """Calculate human-readable uptime from ISO timestamp."""
    if not started_at_str:
        return "-"
    try:
        started = datetime.fromisoformat(started_at_str)
        delta = datetime.now() - started
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            return f"{total_seconds // 60}m {total_seconds % 60}s"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    except Exception:
        return "-"


def cmd_ps(args):
    """List all containers and their status."""

    containers = list_containers()

    if not containers:
        print("No containers found.")
        return

    for c in containers:
        if c["state"] == "running" and not is_pid_alive(c.get("pid")):
            c["state"] = "stopped"
            c["stopped_at"] = datetime.now().isoformat()
            save_state(c["id"], c)

    print(f"{'CONTAINER ID':<16} {'IMAGE':<16} {'COMMAND':<20} {'STATE':<10} {'PID':<8} {'UPTIME'}")
    print("-" * 85)

    for c in containers:
        cid = c.get("id", "?")
        image = c.get("image", "-") or "-"
        cmd_str = " ".join(c.get("command", [])) or "-"
        if len(cmd_str) > 18:
            cmd_str = cmd_str[:15] + "..."
        state = c.get("state", "?")
        pid = str(c.get("pid", "-")) if c.get("pid") else "-"

        if state == "running":
            uptime = format_uptime(c.get("started_at"))
        else:
            uptime = "-"

        print(f"{cid:<16} {image:<16} {cmd_str:<20} {state:<10} {pid:<8} {uptime}")

def cmd_stop(args):
    """Stop a running container by ID."""

    state = load_state(args.container_id)
    if state is None:
        print(f"Error: container '{args.container_id}' not found")
        sys.exit(1)

    if state["state"] != "running":
        print(f"Container '{args.container_id}' is not running (state: {state['state']})")
        return

    pid = state.get("pid")
    if pid is None:
        print(f"Error: no PID recorded for container '{args.container_id}'")
        state["state"] = "stopped"
        state["stopped_at"] = datetime.now().isoformat()
        save_state(args.container_id, state)
        return

    print(f"Stopping {args.container_id}...")

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("Process already exited.")
        state["state"] = "stopped"
        state["stopped_at"] = datetime.now().isoformat()
        save_state(args.container_id, state)
        return

    grace_period = 10
    for i in range(grace_period * 2):
        if not is_pid_alive(pid):
            break
        time.sleep(0.5)

    if is_pid_alive(pid):
        print(f"Process still alive after {grace_period}s, sending SIGKILL...")
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        except ProcessLookupError:
            pass

    state["state"] = "stopped"
    state["stopped_at"] = datetime.now().isoformat()
    save_state(args.container_id, state)

    rootfs = state.get("rootfs")
    cgroup_path = state.get("cgroup_path")
    if rootfs or cgroup_path:
        cleanup(rootfs, cgroup_path, args.container_id)

    print(f"Stopped {args.container_id}")

def cmd_restart(args):
    """Restart a container with the same config."""

    state = load_state(args.container_id)
    if state is None:
        print(f"Error: container '{args.container_id}' not found")
        sys.exit(1)

    image = state.get("image")
    command = state.get("command", [])
    memory_raw = state.get("memory_raw", "50M")
    cpu = state.get("cpu", 50)
    timeout = state.get("timeout", 100)

    if state["state"] == "running":
        args.container_id = state["id"]
        cmd_stop(args)

    run_args = Namespace(
        image=image,
        memory=memory_raw,
        cpu=cpu,
        timeout=timeout,
        cmd=command,
    )

    print(f"Restarting with config from {args.container_id}...")
    cmd_run(run_args)

CLONE_NEWNS  = 0x00020000
CLONE_NEWUTS = 0x04000000
CLONE_NEWNET = 0x40000000

def cmd_exec(args):
    """Execute a command inside a running container."""

    state = load_state(args.container_id)
    if state is None:
        print(f"Error: container '{args.container_id}' not found")
        sys.exit(1)

    if state["state"] != "running":
        print(f"Error: container '{args.container_id}' is not running (state: {state['state']})")
        sys.exit(1)

    pid = state.get("pid")
    if pid is None or not is_pid_alive(pid):
        print(f"Error: container process is not alive")
        sys.exit(1)

    command = [c for c in args.cmd if c != "--"]
    if not command:
        print("Error: no command specified for exec")
        sys.exit(1)

    namespaces = [
        ("mnt", CLONE_NEWNS),
        ("uts", CLONE_NEWUTS),
        ("net", CLONE_NEWNET),
    ]

    child_pid = os.fork()

    if child_pid > 0:
        _, status = os.waitpid(child_pid, 0)
        exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
        sys.exit(exit_code)

    try:
        for ns_name, _ in namespaces:
            ns_path = f"/proc/{pid}/ns/{ns_name}"
            try:
                fd = os.open(ns_path, os.O_RDONLY)
                linux.setns(fd, 0)
                os.close(fd)
            except FileNotFoundError:
                print(f"Warning: namespace {ns_path} not found, skipping")
            except OSError as e:
                print(f"Warning: failed to join {ns_name} namespace: {e}")

        os.chdir("/")

        os.execvp(command[0], command)

    except Exception as e:
        print(f"exec failed: {e}")
        os._exit(1)

def cmd_logs(args):
    """Show logs for a container."""

    log_path = os.path.join(LOG_DIR, f"{args.container_id}.log")
    if not os.path.exists(log_path):
        print(f"No logs found for container '{args.container_id}'")
        sys.exit(1)

    with open(log_path, "r") as f:
        if args.follow:
            f.seek(0, 2)
            print(f"Following logs for {args.container_id} (Ctrl+C to stop)...")
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.3)
            except KeyboardInterrupt:
                print()
        else:
            print(f.read())

def cmd_rm(args):
    """Remove a stopped container's state and logs."""

    state = load_state(args.container_id)
    if state is None:
        print(f"Error: container '{args.container_id}' not found")
        sys.exit(1)

    if state["state"] == "running":
        print(f"Error: container '{args.container_id}' is still running. Stop it first.")
        sys.exit(1)

    state_path = os.path.join(STATE_DIR, f"{args.container_id}.json")
    if os.path.exists(state_path):
        os.remove(state_path)

    log_path = os.path.join(LOG_DIR, f"{args.container_id}.log")
    if os.path.exists(log_path):
        os.remove(log_path)

    print(f"Removed {args.container_id}")

def build_parser():
    parser = argparse.ArgumentParser(
        prog="minicontainer",
        description="Linux container runtime with lifecycle management",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser("run", help="Run a container in the background")
    run_parser.add_argument("--image", type=str, default=None,
                            help="Docker image to pull (e.g. alpine, ubuntu:22.04)")
    run_parser.add_argument("--timeout", type=int, default=100,
                            help="Timeout in seconds (default: 100)")
    run_parser.add_argument("--memory", type=str, default="50M",
                            help="Memory limit (e.g. 50M, 1G)")
    run_parser.add_argument("--cpu", type=int, default=50,
                            help="CPU percent limit (1-100, default: 50)")
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER,
                            help="Command to run inside the container")

    subparsers.add_parser("ps", help="List all containers")

    stop_parser = subparsers.add_parser("stop", help="Stop a running container")
    stop_parser.add_argument("container_id", type=str,
                             help="Container ID to stop")

    restart_parser = subparsers.add_parser("restart", help="Restart a container")
    restart_parser.add_argument("container_id", type=str,
                                help="Container ID to restart")

    exec_parser = subparsers.add_parser("exec", help="Run a command in a running container")
    exec_parser.add_argument("container_id", type=str,
                             help="Container ID to exec into")
    exec_parser.add_argument("cmd", nargs=argparse.REMAINDER,
                             help="Command to execute")

    logs_parser = subparsers.add_parser("logs", help="View container logs")
    logs_parser.add_argument("container_id", type=str,
                             help="Container ID")
    logs_parser.add_argument("-f", "--follow", action="store_true",
                             help="Follow log output (like tail -f)")

    rm_parser = subparsers.add_parser("rm", help="Remove a stopped container")
    rm_parser.add_argument("container_id", type=str,
                           help="Container ID to remove")

    return parser

COMMANDS = {
    "run": cmd_run,
    "ps": cmd_ps,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "exec": cmd_exec,
    "logs": cmd_logs,
    "rm": cmd_rm,
}


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    handler = COMMANDS.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)