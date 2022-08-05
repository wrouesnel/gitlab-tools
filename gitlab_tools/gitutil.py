"""Utility functions for handling constructing git commands"""
from typing import Any, Callable, List, Mapping, Optional

import git
from git import PathLike

from gitlab_tools import config


def clone_from(
    config: config.Config,
    url: PathLike,
    to_path: PathLike,
    progress: Optional[Callable] = None,
    env: Optional[Mapping[str, str]] = None,
    multi_options: Optional[List[str]] = None,
    **kwargs: Any,
) -> git.Repo:
    """Wrap git.clone_from so we can simply pass in the context object and append the correct TLS commands"""
    if multi_options is None:
        multi_options = []
    multi_options = multi_options[:]
    if not config.ssl_verify:
        multi_options.append("--config http.sslVerify=false")
    if config.ssl_capath:
        multi_options.append(f"--config http.sslCAInfo={config.ssl_capath}")
    multi_options = None if len(multi_options) == 0 else multi_options

    return git.Repo.clone_from(url, to_path, multi_options=multi_options)
