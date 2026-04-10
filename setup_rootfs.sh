#!/bin/bash
set -e

ROOTFS_DIR="$1"
if [ -z "$ROOTFS_DIR" ]; then
    echo "Usage: setup_rootfs.sh <path>"
    exit 1
fi

commands=("ls" "cat" "echo" "ps" "mkdir" "rm" "sh" "sleep" "hostname" "ip" "ping")
mkdir -p "$ROOTFS_DIR/usr/bin"

for cmd in "${commands[@]}"; do
    cmd_path=$(which "$cmd")
    cp "$cmd_path" "$ROOTFS_DIR/usr/bin/"
    ldd "$cmd_path" | grep -o '/[^ ]*' | while read lib_path; do
        mkdir -p "$ROOTFS_DIR$(dirname $lib_path)"
        cp "$lib_path" "$ROOTFS_DIR$lib_path"
    done
done

mkdir -p "$ROOTFS_DIR/dev"
mknod -m 666 "$ROOTFS_DIR/dev/null" c 1 3
mknod -m 666 "$ROOTFS_DIR/dev/zero" c 1 5
mknod -m 666 "$ROOTFS_DIR/dev/random" c 1 8
mknod -m 666 "$ROOTFS_DIR/dev/urandom" c 1 9

mkdir -p "$ROOTFS_DIR/proc"
mkdir -p "$ROOTFS_DIR/tmp"

ln -sf usr/bin "$1/bin"