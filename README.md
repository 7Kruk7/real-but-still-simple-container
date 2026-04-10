# Container Runtime from Scratch

A Linux container runtime built from scratch in Python and C, implementing the core mechanisms that Docker uses under the hood.

## What it does

Runs a command in a fully isolated environment with its own filesystem, process tree, hostname, and network — just like `docker run`.

```bash
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/sh -c "ps aux && ping -c 2 8.8.8.8"
```

## How it works

The container uses six Linux kernel mechanisms:

- **Namespaces** — mount (private filesystem), PID (isolated process tree), UTS (custom hostname), network (own IP and interfaces), via `unshare()` syscall
- **pivot_root** — swaps the root filesystem securely, replacing chroot
- **Cgroups v2** — enforces CPU and memory limits by writing to `/sys/fs/cgroup`
- **Overlay filesystem** — copy-on-write layer on top of a read-only base image, so containers don't modify the original
- **Bridge networking** — veth pairs, a Linux bridge, and iptables NAT give each container its own IP with internet access
- **C extension** — `linux.c` wraps syscalls (`unshare`, `mount`, `pivot_root`, `setns`, `sethostname`, `umount`, `umount2`) that Python doesn't expose natively

## Building

```bash
sudo apt install build-essential python3-dev iptables
python3 setup.py build_ext --inplace
```

## Usage

```bash
# Run a command in isolation
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/ls /

# Check process isolation
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/ps aux

# Check network isolation
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/sh -c "ip addr show"

# Ping the internet from inside the container
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/sh -c "ping -c 2 8.8.8.8"
```

## Project structure

```
container.py       — Main Python CLI and container runtime
linux.c            — C extension wrapping Linux namespace syscalls
setup.py           — Build script for the C extension
setup_rootfs.sh    — Bash script that prepares the base filesystem image
test_linux.py      — Tests for the C extension
```

## Requirements

- Linux (tested on Ubuntu 24.04 / WSL2)
- Python 3.10+
- Root privileges (sudo)
- build-essential and python3-dev (for compiling the C extension)
- iptables (for container networking)

## Limitations

- No user namespace (container runs as real root)
- No seccomp syscall filtering
- No OCI image support (uses a custom rootfs, not Docker images)
- No container lifecycle management (start/stop/exec)
- Networking bridge and iptables rules persist until manually removed or reboot

## Architecture

```
sudo python3 container.py run -- /usr/bin/ls
         |
         v
    setup_bridge()        — Create bridge + iptables NAT (one-time)
    setup_rootfs()        — Mount overlay (base image + writable layer)
    setup_cgroups()       — Write CPU/memory limits
         |
         v
    os.fork()
         |
    Child:                          Parent:
      unshare(NEWNET)                 wait for child signal
      signal parent                   setup_network() — veth pair, bridge, IPs
      wait for parent                 signal child
      pivot_root()                    waitpid()
      unshare(NEWPID)
      fork() → PID 1
        mount /proc
        execvp(command)
```

## Inspired by

- [rubber-docker](https://github.com/Fewbytes/rubber-docker) — Workshop on rebuilding Docker from scratch
- Docker Deep Dive by Nigel Poulton
- [Linux Namespaces guide](https://linuxhandbook.com/namespaces/)
