import pytest
from minicontainer import parse_memory

def test__50M():
    result = parse_memory("50M")
    assert result == 52428800

def test_1G():
    result = parse_memory("1G")
    assert result == 1073741824

def test_500K():
    result = parse_memory("500K")
    assert result == 512000

def test_1024():
    result = parse_memory("1024")
    assert result == 1024 

def test_unkown_unit():
    with pytest.raises(ValueError):
        parse_memory("50X")

def test_negative_memory():
    with pytest.raises(ValueError):
        parse_memory("-50M")

def test_empty_string():
    with pytest.raises((ValueError, IndexError)):
        parse_memory("")