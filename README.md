# Container Runtime from Scratch

A Linux container runtime built from scratch in Python and C, implementing the core mechanisms that Docker uses under the hood. Pulls real images from Docker Hub and runs them in fully isolated environments.

## What it does

Runs a command in a fully isolated environment with its own filesystem, process tree, hostname, network, and resource limits – just like `docker run`.

```bash
# Pull Alpine from Docker Hub and run a shell inside it
sudo python3 container.py run --image alpine --memory 50M --cpu 50 -- /bin/sh

# Run with a custom base filesystem instead of a Docker image
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/ls /
```

## How it works

The container uses seven Linux kernel mechanisms, each implemented as a separate phase:

**Phase 1 – C extension** wraps syscalls that Python does not expose natively (`unshare`, `mount`, `pivot_root`, `setns`, `sethostname`, `umount`, `umount2`, `capset`, `capdrop`). Compiled with `setup.py` into a shared library that `container.py` imports.

**Phase 2 – Mount namespace + pivot_root** replaces `chroot` with a secure root filesystem swap. The container process calls `unshare(CLONE_NEWNS)` for a private mount tree, then `pivot_root()` to make the new root permanent. The host filesystem becomes completely invisible.

**Phase 3 – PID + UTS namespaces** give the container its own process tree (PID 1 inside) and its own hostname. The container cannot see or signal host processes.

**Phase 4 – Overlay filesystem** stacks a writable layer on top of a read-only base image using the kernel's `overlayfs`. Changes inside the container do not modify the original image – the same image can be shared across multiple containers.

**Phase 5 – Network namespace** creates an isolated network stack for each container. A veth pair connects the container to a Linux bridge (`br0`) on the host, and iptables NAT rules provide internet access. Each container gets its own IP address in the `10.0.0.0/24` subnet.

**Phase 6 – Security hardening** drops Linux capabilities to match Docker's default whitelist (14 out of 41). Even though the container runs as root, dangerous operations like loading kernel modules, rebooting, or changing the system clock are blocked.

**Phase 7 – OCI image support** pulls real Docker images from Docker Hub using the Registry HTTP API v2. The process authenticates with a bearer token, resolves multi-arch manifest lists to the `linux/amd64` platform, downloads each layer blob (handling CDN redirects), and extracts the gzipped tar layers into the image directory.

## Building

```bash
# Install dependencies
sudo apt install build-essential python3-dev iptables

# Compile the C extension
python3 setup.py build_ext --inplace
```

## Usage

```bash
# Run Alpine Linux from Docker Hub
sudo python3 container.py run --image alpine --memory 50M --cpu 50 -- /bin/sh

# Run Ubuntu from Docker Hub
sudo python3 container.py run --image ubuntu --memory 100M --cpu 50 -- /bin/bash

# Run with a specific image tag
sudo python3 container.py run --image alpine:3.19 --memory 50M --cpu 50 -- /bin/sh

# Run with custom base filesystem (no Docker image)
sudo python3 container.py run --memory 50M --cpu 50 -- /usr/bin/ps aux

# Check process isolation
sudo python3 container.py run --image alpine --memory 50M --cpu 50 -- /bin/ps aux

# Check network isolation
sudo python3 container.py run --image alpine --memory 50M --cpu 50 -- /bin/sh -c "ip addr show"

# Ping the internet from inside the container
sudo python3 container.py run --image alpine --memory 50M --cpu 50 -- /bin/sh -c "ping -c 2 8.8.8.8"
```

### CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--image` | none | Docker image to pull (e.g. `alpine`, `ubuntu:22.04`) |
| `--memory` | `50M` | Memory limit (`K`, `M`, `G` suffixes or plain bytes) |
| `--cpu` | `10` | CPU limit as percentage (1–100) |
| `--timeout` | `100` | Timeout in seconds |
| `--log` | none | Log file path |

## Project structure

```
container.py       – Main Python CLI and container runtime
linux.c            – C extension wrapping Linux namespace syscalls
setup.py           – Build script for the C extension
setup_rootfs.sh    – Bash script that prepares a fallback base filesystem
test_linux.py      – Tests for the C extension
tests/             – Pytest test suite
```

## Architecture

```
sudo python3 container.py run --image alpine -- /bin/sh
         |
         v
    setup_bridge()        – Create bridge + iptables NAT (one-time)
    pull_imagine()        – Auth to Docker Hub, fetch manifest, download layers
    setup_rootfs()        – Mount overlay (image layers + writable layer)
    setup_cgroups()       – Write CPU/memory limits to cgroup v2
         |
         v
    os.fork()
         |
    Child:                          Parent:
      unshare(NEWNET)                 wait for child signal
      signal parent                   setup_network() – veth pair, bridge, IPs
      wait for parent                 signal child
      pivot_root()                    waitpid()
      unshare(NEWPID)
      fork() -> PID 1
        mount /proc
        drop_capabilities()
        execvp(command)
```

### Image pull flow

```
pull_imagine("alpine")
         |
         v
    1. GET auth.docker.io/token        – Get bearer token (anonymous for public images)
         |
         v
    2. GET registry-1.docker.io         – Fetch manifest by tag
       /v2/library/alpine/manifests/latest
         |
         v
    3. Manifest list?                   – If multi-arch, pick linux/amd64 digest
       yes -> fetch again by digest     – Get single-platform manifest with layers
         |
         v
    4. For each layer:
       GET /v2/.../blobs/sha256:...     – Registry returns 302 redirect to CDN
       Follow redirect WITHOUT auth     – CDN rejects Authorization header
       Extract gzipped tar to image_dir
```

## Requirements

- Linux (tested on Ubuntu 24.04 / WSL2)
- Python 3.10+
- Root privileges (sudo)
- build-essential and python3-dev (for compiling the C extension)
- iptables (for container networking)
- Internet access (for pulling Docker images)

## Limitations

- No user namespace (container runs as real root)
- No seccomp syscall filtering
- No container lifecycle management (start/stop/exec)
- Networking bridge and iptables rules persist until manually removed or reboot
- Images are re-downloaded on each run (no local image cache with deduplication)

## Running tests

```bash
pytest tests/ -v
```

## Inspired by

- [rubber-docker](https://github.com/Fewbytes/rubber-docker) – Workshop on rebuilding Docker from scratch
- *Docker Deep Dive* by Nigel Poulton
- [Linux Namespaces guide](https://linuxhandbook.com/namespaces/)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)
- [dxf](https://github.com/davedoesdev/dxf) – Docker Registry v2 client in Python
