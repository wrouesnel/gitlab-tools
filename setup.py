#!/usr/bin/env python3.6

import os
import sys

try:
    from setuptools import setup, find_packages
except ImportError:
    print("Please install setuptools.")
    sys.exit(1)

if sys.version_info < (3, 5):
    sys.exit("Sorry, Python < 3.5 is not supported")

version_raw = os.environ.get("VERSION", None)
if version_raw is None:
    version_raw = open("VERSION").read()

version = version_raw.split("-")

pypi_version = version[0] + "+" + ".".join(version[1:])

print("Setting package version to:", pypi_version.strip())

setup(
    name="wrouesnel-gitlab-tools",
    version=pypi_version,
    description="gitlab tools and scripts wrapper package",
    author="Will Rouesnel",
    author_email="wrouesnel@wrouesnel.com",
    url="",
    install_requires=["python-gitlab", "structlog", "lxml", "beautifulsoup4", "pyotp"],
    packages=find_packages("."),
    package_data={"": ["VERSION"]},
    entry_points={"console_scripts": ["gitlab-tools=gitlab_tools.__main__:main"]},
    classifiers=[
        "License :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
    ],
)
