import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from minicontainer import setup_cgroups

needs_root = pytest.mark.skipif(os.getuid() != 0, reason="Requires root")

@needs_root
def test_cgroup_directory_created():
    path = setup_cgroups("test-cgroup-01", 52428800, 50)
    assert os.path.isdir(path)
    os.rmdir(path)

@needs_root
def test_memory_max_value():
    path = setup_cgroups("test-cgroup-02", 52428800, 50)
    with open(f"{path}/memory.max") as f:
        assert f.read().strip() == "52428800"
    os.rmdir(path)

@needs_root
def test_memory_max_1g():
    path = setup_cgroups("test-cgroup-03", 1073741824, 50)
    with open(f"{path}/memory.max") as f:
        assert f.read().strip() == "1073741824"
    os.rmdir(path)

@needs_root
def test_cpu_max_50_percent():
    path = setup_cgroups("test-cgroup-04", 52428800, 50)
    with open(f"{path}/cpu.max") as f:
        content = f.read().strip()
        quota, period = content.split()
        assert quota == "50000"
        assert period == "100000"
    os.rmdir(path)

@needs_root
def test_cpu_max_100_percent():
    path = setup_cgroups("test-cgroup-05", 52428800, 100)
    with open(f"{path}/cpu.max") as f:
        content = f.read().strip()
        quota, period = content.split()
        assert quota == "100000"
        assert period == "100000"
    os.rmdir(path)

@needs_root
def test_cpu_max_25_percent():
    path = setup_cgroups("test-cgroup-06", 52428800, 25)
    with open(f"{path}/cpu.max") as f:
        content = f.read().strip()
        quota, period = content.split()
        assert quota == "25000"
        assert period == "100000"
    os.rmdir(path)

@needs_root
def test_cgroup_cleanup():
    path = setup_cgroups("test-cgroup-07", 52428800, 50)
    assert os.path.isdir(path)
    os.rmdir(path)
    assert not os.path.exists(path)