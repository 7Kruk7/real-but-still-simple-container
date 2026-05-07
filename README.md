# Container Runtime from Scratch

A Linux container runtime built from scratch in Python and C, implementing the core mechanisms that Docker uses under the hood. Pulls real images from Docker Hub and runs them in fully isolated environments with lifecycle management.

## What it does

Runs a command in a fully isolated environment with its own filesystem, process tree, hostname, network, and resource limits - just like `docker run`.

```bash
# Run a container in the background (daemonized)
sudo python3 lifecycle.py run --image alpine --memory 50M --cpu 50 -- /bin/sleep 300

# List running containers
sudo python3 lifecycle.py ps

# Execute a command inside a running container
sudo python3 lifecycle.py exec mc-6ee7908c -- /bin/sh

# View container logs
sudo python3 lifecycle.py logs mc-6ee7908c

# Follow logs in real time (like tail -f)
sudo python3 lifecycle.py logs -f mc-6ee7908c

# Stop a running container (SIGTERM then SIGKILL)
sudo python3 lifecycle.py stop mc-6ee7908c

# Restart with the same config
sudo python3 lifecycle.py restart mc-6ee7908c

# Remove a stopped container's state and logs
sudo python3 lifecycle.py rm mc-6ee7908c
```

## How it works

The container runtime uses eight Linux kernel mechanisms, each implemented as a separate phase:

**Phase 1 - C extension** wraps syscalls that Python does not expose natively (`unshare`, `mount`, `pivot_root`, `setns`, `sethostname`, `umount`, `umount2`, `capset`, `capdrop`). Compiled with `setup.py` into a shared library that the runtime imports.

**Phase 2 - Mount namespace + pivot_root** replaces `chroot` with a secure root filesystem swap. The container process calls `unshare(CLONE_NEWNS)` for a private mount tree, then `pivot_root()` to make the new root permanent. The host filesystem becomes completely invisible.

**Phase 3 - PID + UTS namespaces** give the container its own process tree (PID 1 inside) and its own hostname. The container cannot see or signal host processes.

**Phase 4 - Overlay filesystem** stacks a read-only base image with a writable upper layer using OverlayFS. Changes inside the container do not modify the base image - the same mechanism Docker uses for copy-on-write.

**Phase 5 - Network namespace** creates an isolated network stack for each container. A veth pair connects the container to a host bridge (`br0`), with iptables NAT rules providing internet access. Each container gets its own IP address in the `10.0.0.0/24` subnet.

**Phase 6 - Security hardening** drops Linux capabilities to Docker's default set of 14 (from 41). Even root inside the container cannot load kernel modules, reboot the host, or reconfigure networking.

**Phase 7 - OCI image pulling** downloads real Docker images from Docker Hub using the Registry v2 API. Authenticates with a bearer token, fetches the manifest, resolves multi-arch images to `linux/amd64`, downloads and extracts each gzipped layer into the image directory.

**Phase 8 - Lifecycle management** adds daemonization and container lifecycle commands. Part 1 persists container state as JSON files in `/var/lib/minicontainer/containers/`. Part 2 (current) introduces a new CLI entry point (`lifecycle.py`) with `run`, `ps`, `stop`, `restart`, `exec`, `logs`, and `rm` commands. Containers run in the background using the double-fork daemon pattern, and `exec` uses `setns()` to join a running container's namespaces.

## Image pull flow

```
    1. GET auth.docker.io/token        - Get bearer token (anonymous for public images)
         |
         v
    2. GET registry-1.docker.io         - Fetch manifest by tag
       /v2/library/alpine/manifests/latest
         |
         v
    3. Manifest list?                   - If multi-arch, pick linux/amd64 digest
       yes -> fetch again by digest     - Get single-platform manifest with layers
         |
         v
    4. For each layer:
       GET /v2/.../blobs/sha256:...     - Registry returns 302 redirect to CDN
       Follow redirect WITHOUT auth     - CDN rejects Authorization header
       Extract gzipped tar to image_dir
```

## Container lifecycle

```
    lifecycle.py run --image alpine -- /bin/sh
         |
         v
    Double fork (daemonize)
    Parent prints container ID, returns to terminal
         |
         v
    Daemon process (grandchild):
      setup_bridge()       - Create bridge + iptables NAT (one-time)
      setup_rootfs()       - Mount overlay (base image + writable layer)
      setup_cgroups()      - Write CPU/memory limits
      save_state()         - Persist container info as JSON
         |
         v
    os.fork()
         |
    Child:                          Parent (daemon):
      unshare(NEWNS, NEWUTS, NEWNET)  wait for child signal
      signal parent                   setup_network() - veth pair, bridge, IPs
      wait for parent                 signal child
      pivot_root()                    monitor (waitpid + VmRSS)
      unshare(NEWPID)                 update state on exit
      fork() -> PID 1                 cleanup on stop
        mount /proc
        drop_capabilities()
        execvp(command)
```

## Project structure

```
lifecycle.py       - CLI entry point with lifecycle commands (run, ps, stop, restart, exec, logs, rm)
container.py       - Core container runtime (namespaces, cgroups, overlay, networking)
linux.c            - C extension wrapping Linux syscalls
setup.py           - Build script for the C extension
setup_rootfs.sh    - Bash script that prepares the base filesystem image (fallback when no --image)
tests/             - pytest tests for memory parsing, cgroups, cleanup
```

## Requirements

- Linux (tested on Ubuntu 24.04 / WSL2)
- Python 3.10+
- Root privileges (sudo)
- build-essential and python3-dev (for compiling the C extension)
- iptables (for container networking)
- Internet access (for pulling Docker images)

## Setup

```bash
# Build the C extension
sudo python3 setup.py build_ext --inplace

# Run tests
pytest tests/ -v
```

## Limitations

- No user namespace (container runs as real root)
- No seccomp syscall filtering
- Networking bridge and iptables rules persist until manually removed or reboot
- Images are re-downloaded on each run (no local image cache with deduplication)
- `exec` currently joins mount namespace only (UTS and NET namespace fds not propagated from inner child)
- `restart` creates a new container ID rather than reusing the old one

## What I learned

Building this project taught me how containers actually work under the hood:

- There is no single kernel feature called "container" - it is a combination of namespaces, cgroups, and filesystem tricks applied to ordinary processes
- Docker's architecture is modular: the CLI talks to the daemon, the daemon talks to containerd, and containerd uses runc to create containers. runc does the actual container creation using the same kernel primitives this project uses
- cgroups are managed entirely through the filesystem - creating directories and writing values to files, no special syscalls needed
- The fork/exec model is fundamental to process creation in Linux, and the gap between fork and exec is where all container isolation gets applied
- The double-fork daemon pattern detaches a process from the terminal by ensuring the final process is not a session leader and cannot reacquire a controlling terminal
- `setns()` is how `docker exec` works - it opens `/proc/<pid>/ns/*` files and joins each namespace, then execs the command inside
- OCI image pulling is just HTTP requests: auth token, manifest fetch, layer download from a CDN redirect - no special protocol

## Inspired by

- [rubber-docker](https://github.com/Fewbytes/rubber-docker) - Workshop on rebuilding Docker from scratch
- *Docker Deep Dive* by Nigel Poulton
- [Linux Namespaces guide](https://linuxhandbook.com/namespaces/)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)
- [Linux kernel cgroups documentation](https://www.kernel.org/doc/Documentation/cgroup-v2.txt)
