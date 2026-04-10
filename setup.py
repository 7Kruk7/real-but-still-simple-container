from setuptools import setup, Extension

setup(
    name="linux",
    version="1.0",
    ext_modules=[
        Extension("linux", sources=["linux.c"])
    ]
)