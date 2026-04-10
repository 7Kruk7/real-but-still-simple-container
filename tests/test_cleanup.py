import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from minicontainer import cleanup

def test_cleanup_removes_rootfs_directory():
    tmp = tempfile.mkdtemp(prefix="minicontainer-test-")
    rootfs = os.path.join(tmp, "rootfs")
    os.makedirs(rootfs)
    os.makedirs(os.path.join(rootfs, "proc"))
    with open(os.path.join(rootfs, "testfile"), "w") as f:
        f.write("test")
    cleanup(rootfs, "/sys/fs/cgroup/nonexistent-path")
    assert not os.path.exists(tmp)

def test_cleanup_handles_missing_rootfs():
    cleanup("/tmp/nonexistent-rootfs-abc123/rootfs", "/sys/fs/cgroup/nonexistent-path")

def test_cleanup_handles_missing_cgroup():
    tmp = tempfile.mkdtemp(prefix="minicontainer-test-")
    rootfs = os.path.join(tmp, "rootfs")
    os.makedirs(rootfs)
    cleanup(rootfs, "/sys/fs/cgroup/nonexistent-cgroup-xyz")
    assert not os.path.exists(tmp)

def test_cleanup_handles_none_values():
    try:
        cleanup(None, None)
    except TypeError:
        pass 

def test_cleanup_handles_already_unmounted_proc():
    tmp = tempfile.mkdtemp(prefix="minicontainer-test-")
    rootfs = os.path.join(tmp, "rootfs")
    os.makedirs(os.path.join(rootfs, "proc"))
    cleanup(rootfs, "/sys/fs/cgroup/nonexistent-path")
    assert not os.path.exists(tmp)