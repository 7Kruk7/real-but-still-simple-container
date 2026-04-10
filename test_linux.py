import linux
import os
import sys

def test_module_loads():
    """Test that all functions and constants exist"""
    assert hasattr(linux, 'unshare')
    assert hasattr(linux, 'mount')
    assert hasattr(linux, 'umount')
    assert hasattr(linux, 'umount2')
    assert hasattr(linux, 'pivot_root')
    assert hasattr(linux, 'setns')
    assert hasattr(linux, 'sethostname')
    print("PASS: All functions exist")

    assert hasattr(linux, 'CLONE_NEWPID')
    assert hasattr(linux, 'CLONE_NEWUTS')
    assert hasattr(linux, 'CLONE_NEWNS')
    assert hasattr(linux, 'CLONE_NEWNET')
    assert hasattr(linux, 'CLONE_NEWIPC')
    assert hasattr(linux, 'CLONE_NEWUSER')
    assert hasattr(linux, 'MS_BIND')
    assert hasattr(linux, 'MNT_DETACH')
    print("PASS: All constants exist")

def test_unshare_uts():
    """Test UTS namespace isolation"""
    original = os.uname().nodename
    pid = os.fork()
    if pid == 0:
        linux.unshare(linux.CLONE_NEWUTS)
        linux.sethostname("test-container")
        hostname = os.uname().nodename
        if hostname == "test-container":
            os._exit(0)
        else:
            os._exit(1)
    else:
        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        assert os.uname().nodename == original
        print("PASS: unshare + sethostname works")

def test_mount_umount():
    """Test mount and umount"""
    test_dir = "/tmp/test_linux_ext"
    os.makedirs(test_dir, exist_ok=True)
    linux.mount("tmpfs", test_dir, "tmpfs", 0, "")
    with open("/proc/mounts") as f:
        assert test_dir in f.read()
    linux.umount(test_dir)
    os.rmdir(test_dir)
    print("PASS: mount + umount works")

def test_error_handling():
    """Test that bad syscalls raise exceptions"""
    try:
        linux.mount("none", "/nonexistent", "proc", 0, "")
        print("FAIL: Should have raised an error")
        sys.exit(1)
    except (RuntimeError, OSError):
        print("PASS: Error handling works")

if __name__ == "__main__":
    test_module_loads()
    test_unshare_uts()
    test_mount_umount()
    test_error_handling()
    print("\nAll tests passed!")