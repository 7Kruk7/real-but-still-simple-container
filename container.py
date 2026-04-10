import argparse
import os
import uuid
import subprocess
import shutil
import logging
import time
import signal
import linux

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

def setup_rootfs(container_id: str) -> str:
    container_dir = f"/tmp/minicontainer-{container_id}"
    image_dir = "/var/lib/minicontainer/images/base"

    upper = f"{container_dir}/upper"
    work = f"{container_dir}/work"
    merged = f"{container_dir}/merged"

    try:
        os.makedirs(upper)
        os.makedirs(work)
        os.makedirs(merged)

        if not os.path.exists(image_dir):
            os.makedirs(image_dir)
            subprocess.run(["bash", "setup_rootfs.sh", image_dir], check=True)

        linux.mount(
            "overlay",
            merged,
            "overlay",
            0,
            f"lowerdir={image_dir},upperdir={upper},workdir={work}"
        )
    except FileExistsError:
        print(f"Directory '{container_dir}' already exists.")
    except PermissionError:
        print(f"Permission denied: Unable to create directories.")
    except RuntimeError as e:
        print(f"Failed to mount overlay: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    return merged

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

def setup_bridge():
    """Create the bridge network if it doesn't exist"""
    result = subprocess.run(["ip", "link", "show", "br0"], capture_output=True)
    if result.returncode != 0:
        subprocess.run(["ip", "link", "add", "br0", "type", "bridge"], check=True)
        subprocess.run(["ip", "addr", "add", "10.0.0.1/24", "dev", "br0"], check=True)
        subprocess.run(["ip", "link", "set", "br0", "up"], check=True)

        with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
            f.write("1")

        subprocess.run([
            "iptables", "-t", "nat", "-A", "POSTROUTING",
            "-s", "10.0.0.0/24", "!", "-o", "br0",
            "-j", "MASQUERADE"
        ], check=True)
        subprocess.run([
            "iptables", "-A", "FORWARD", "-i", "br0", "-j", "ACCEPT"
        ], check=True)
        subprocess.run([
            "iptables", "-A", "FORWARD", "-o", "br0",
            "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"
        ], check=True)
        logging.info("Bridge br0 created")

def setup_network(container_id, container_pid):
    short_id = container_id[-8:]
    veth_host = f"veth-{short_id}"
    veth_container = f"ceth-{short_id}"

    subprocess.run([
        "ip", "link", "add", veth_host,
        "type", "veth", "peer", "name", veth_container
    ], check=True)

    subprocess.run([
        "ip", "link", "set", veth_container,
        "netns", str(container_pid)
    ], check=True)

    subprocess.run(["ip", "link", "set", veth_host, "master", "br0"], check=True)
    subprocess.run(["ip", "link", "set", veth_host, "up"], check=True)

    container_ip = f"10.0.0.{(container_pid % 253) + 2}"
    nsenter = ["nsenter", f"--net=/proc/{container_pid}/ns/net"]

    subprocess.run(nsenter + ["ip", "link", "set", veth_container, "name", "eth0"], check=True)
    subprocess.run(nsenter + ["ip", "addr", "add", f"{container_ip}/24", "dev", "eth0"], check=True)
    subprocess.run(nsenter + ["ip", "link", "set", "eth0", "up"], check=True)
    subprocess.run(nsenter + ["ip", "link", "set", "lo", "up"], check=True)
    subprocess.run(nsenter + ["ip", "route", "add", "default", "via", "10.0.0.1"], check=True)

    logging.info(f"Container network: {container_ip}")
    return container_ip

def run(rootfs, cgroup_path, command, timeout, container_id):
    start_time = time.time()
    child_ready_r, child_ready_w = os.pipe()
    parent_done_r, parent_done_w = os.pipe()

    linux.unshare(linux.CLONE_NEWNS | linux.CLONE_NEWUTS)
    pid = os.fork()

    if pid == 0:
        os.close(child_ready_r)
        os.close(parent_done_w)

        linux.unshare(linux.CLONE_NEWNET)

        os.write(child_ready_w, b"x")
        os.close(child_ready_w)

        os.read(parent_done_r, 1)
        os.close(parent_done_r)

        with open(f"{cgroup_path}/cgroup.procs", "w") as f:
            f.write("0")

        linux.sethostname(container_id)
        linux.mount(None, "/", None, linux.MS_REC | linux.MS_PRIVATE, None)
        linux.mount(rootfs, rootfs, None, linux.MS_BIND, None)
        old_root = os.path.join(rootfs, ".old_root")
        os.makedirs(old_root, exist_ok=True)
        linux.pivot_root(rootfs, old_root)
        os.chdir("/")
        linux.umount2("/.old_root", linux.MNT_DETACH)
        os.rmdir("/.old_root")

        linux.unshare(linux.CLONE_NEWPID)
        inner_pid = os.fork()

        if inner_pid == 0:
            linux.mount("proc", "/proc", "proc", 0, "")
            os.execvp(command[0], command)
        else:
            _, status = os.waitpid(inner_pid, 0)
            os._exit(os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1)
    else:
        os.close(child_ready_w)
        os.close(parent_done_r)

        os.read(child_ready_r, 1)
        os.close(child_ready_r)

        try:
            setup_network(container_id, pid)
        except Exception as e:
            logging.error(f"Network setup failed: {e}")

        os.write(parent_done_w, b"x")
        os.close(parent_done_w)

        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            logging.info(f"Child's exit code: {os.WEXITSTATUS(status)}")

            time.sleep(0.5)
        
def cleanup(rootfs, cgroup_path, container_id):
    short_id = container_id[-8:]
    try:
        subprocess.run(["ip", "link", "del", f"veth-{short_id}"], check=False)
    except Exception:
        pass
    try:
        subprocess.run(["umount", rootfs], check=False)
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
    rootfs = None
    cgroup_path = None
    try:
        setup_bridge()
        rootfs = setup_rootfs(container_id)
        logging.info(f"Rootfs created at: {rootfs}")
        cgroup_path = setup_cgroups(container_id, config["memory"], config["cpu"])
        run(rootfs, cgroup_path, config["cmd"], config["timeout"], container_id)
    finally:
        if rootfs or cgroup_path:
            cleanup(rootfs, cgroup_path, container_id)