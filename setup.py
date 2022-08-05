#!/usr/bin/env python3.6

import os
import sys

try:
    from setuptools import find_packages, setup
except ImportError:
    print("Please install setuptools.")
    sys.exit(1)

if sys.version_info < (3, 7):
    sys.exit("Sorry, Python < 3.7 is not supported")

version_raw = os.environ.get("VERSION", None)
if version_raw is None:
    version_raw = open("VERSION").read()

version = version_raw.split("-")

pypi_version = version[0] + "+" + ".".join(version[1:])

print("Setting package version to:", pypi_version.strip())

install_requires = []
with open("requirements.txt", "rt") as f:
    for line in f:
        if line == "":
            continue
        if line.startswith("#"):
            continue
        if line.startswith("-") or line.startswith("--"):
            continue
        split_line = line.split()
        if len(split_line) > 0:
            install_requires.append(split_line[0])

setup(
    name="wrouesnel-gitlab-tools",
    version=pypi_version,
    description="gitlab tools and scripts wrapper package",
    author="Will Rouesnel",
    author_email="wrouesnel@wrouesnel.com",
    url="",
    install_requires=install_requires,
    include_package_data=True,
    packages=find_packages("."),
    package_data={"": ["VERSION"]},
    entry_points={"console_scripts": ["gitlab-tools=gitlab_tools.__main__:main"]},
    classifiers=[
        "License :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
    ],
)
