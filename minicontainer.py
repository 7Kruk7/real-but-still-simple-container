import argparse
import os
import uuid
import subprocess
import shutil
import logging
import time
import signal

def parse_memory(value : str) -> int:
    number = int(value[:-1])
    if number <= 0:
        raise ValueError("Memory must be a positive intiger value")
    
    unit = value[-1]
    
    if unit == 'K':
        return int(value[:-1]) * 1024
    elif unit == 'M':
        return int(value[:-1]) * 1024 ** 2
    elif unit =='G':
        return int(value[:-1]) * 1024 ** 3
    elif unit.isdigit():
        return int(value)
    else:
        raise ValueError("Unknow unit. Try K, M, G, or plain intiger")
    
def parsering_logic() -> dict:
    """Create the dictionary for further analytics"""

    parser = argparse.ArgumentParser(
                        prog='Miniconatiner',
                        description='Simple process isolator')

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser('run', help='Run a process in isolation')

    run_parser.add_argument("--timeout", type=int, default = 100)
    run_parser.add_argument("--memory", type=str, default = '50M') 
    run_parser.add_argument("--cpu", type=int, default = 10)
    run_parser.add_argument("--log", type=str, default = None)
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    config = {}

    if args.command == "run":
        config = {"timeout" : int(args.timeout),
                "memory" : int(parse_memory(args.memory)),
                "cpu" : int(args.cpu),
                "log" : args.log,
                "cmd" : [c for c in args.cmd if c != "--"]}

    return config

def setup_rootfs(container_id : str) -> str:
    """Create a directory for isolated process"""
    container_dir = f"/tmp/minicontainer-{container_id}"
    rootfs = f"{container_dir}/rootfs"
    try:
        os.makedirs(rootfs)
        subprocess.run(["bash", "setup_rootfs.sh", rootfs], check=True)
        subprocess.run(["mount", "-t", "proc", "proc", f"{rootfs}/proc"], check=True)
    except FileExistsError:
        print(f"Directory '{rootfs}' already exists.")
    except PermissionError:
        print(f"Permission denied: Unable to create '{rootfs}'.")
    except Exception as e:
        print(f"An error occurred: {e}")
    return rootfs

def setup_cgroups(container_id : str, memory_bytes : int, cpu_percent : int) -> str:
    if cpu_percent < 1 or cpu_percent > 100:
            raise ValueError("CPU percent must be between 1 and 100")
    
    cgroup_path = f"/sys/fs/cgroup/minicontainer-{container_id}"
    os.makedirs(cgroup_path)

    with open(f"{cgroup_path}/memory.max", "w") as f:
        f.write(str(memory_bytes))

    quota = int(100000 * cpu_percent / 100)
    with open(f"{cgroup_path}/cpu.max", "w") as f:
        f.write(f"{quota} 100000")

    return cgroup_path

def run(rootfs : str, cgroup_path : str, command : str, timeout : int) -> None:
    """Creating the fork and exec to create a proces isolator"""
    start_time = time.time()
    pid = os.fork()

    if pid == 0:
        with open(f"{cgroup_path}/cgroup.procs", "w") as f:
            f.write("0")

        os.chroot(rootfs)
        os.chdir("/")
        os.execvp(command[0], command)
    else:
        while True:
            child_pid, status = os.waitpid(pid, os.WNOHANG)
            
            if child_pid != 0:
                if os.WIFEXITED(status):
                    code = os.WEXITSTATUS(status)
                    logging.info(f"Child's exit code: {code}")
                else:
                    logging.info("First child does not exited using exit(2) system call.")
                break
            
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if "VmRSS" in line:
                        logging.info(line.strip())
                        break
                    
            elapsed = time.time() - start_time

            if elapsed > timeout:
                logging.info(f"Timeout ({timeout}s) exceeded, sending SIGTERM")
                os.kill(pid, signal.SIGTERM)
                time.sleep(5)
                try:
                    os.kill(pid, 0)
                    logging.info("Process still alive, sending SIGKILL")
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    logging.info("Process terminated after SIGTERM")
                break
            
            time.sleep(0.5)
        

def cleanup(rootfs, cgroup_path):
    try:
        subprocess.run(["umount", f"{rootfs}/proc"], check=False)
    except Exception:
        pass
    try:
        shutil.rmtree(os.path.dirname(rootfs))
    except Exception:
        pass
    try:
        os.rmdir(cgroup_path)
    except Exception:
        pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler("log.log")])

    container_id = "mc-" + uuid.uuid4().hex[:8]
    config = parsering_logic()
    logging.info(config)
    try:
        rootfs = setup_rootfs(container_id)
        logging.info(f"Rootfs created at: {rootfs}")
        cgroup_path = setup_cgroups(container_id, config["memory"], config["cpu"])
        run(rootfs, cgroup_path, config["cmd"], config["timeout"])
    finally:
        cleanup(rootfs, cgroup_path)