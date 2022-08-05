#!/usr/bin/env python3
"""self-service gitlab automation for wrouesnel. Solving problems for me."""
import json
import os
import re
from typing import List, Optional

import click
import git
import ruamel.yaml as yaml
import structlog

from . import clitypes, config, gitutil
from .uiclient.uiclient import GitlabUIClient

logger: structlog.BoundLogger = structlog.getLogger()

DEFAULT_LOGGING = "debug"


@click.group(context_settings={"auto_envvar_prefix": "GITLAB_TOOLS"})
@click.option("--log-level", default="debug", type=click.Choice(config.log_levels()))
@click.option(
    "--ssl-verify/--ssl-no-verify",
    default=True,
    help="Enable SSL authentication",
    show_default=True,
)
@click.option(
    "--ssl-capath",
    help="Path to SSL Certificate Authority to use for verification",
    show_default=True,
)
@click.option(
    "--gitlab-server",
    default="https://gitlab.com",
    help="Gitlab server to clone from",
    show_default=True,
)
@click.option("--user", default=None, help="Specify a user to clone as otherwise use the default")
@click.option(
    "--interactive/--not-interactive",
    default=True,
    help="Allow interactive prompting",
    show_default=True,
)
@click.pass_context
def cli(ctx, log_level, ssl_verify, ssl_capath, gitlab_server, user, interactive):
    config.configure_logging(log_level)
    ctx.obj = config.Config(
        gitlab_server, user, ssl_verify, ssl_capath=ssl_capath, allow_prompting=interactive
    )


@cli.command("clone-organization")
@click.argument("target_org")
@click.pass_obj
def gitlab_org_clone(obj: config.Config, target_org):
    """Clone a lot of repositories out of bitbucket. Currently depends on my unpublished library fork."""
    print("Cloning for {}".format(target_org))
    c = obj.get_gitlab_client()
    print("Authenticated successfully")

    g = c.groups.get(target_org)

    pids = [
        (p.attributes["path"], p.attributes["http_url_to_repo"]) for p in g.projects.list(all=True)
    ]

    print("Found {} repos to clone".format(len(pids)))

    for name, clone_link in pids:
        # Check the repo isn't already cloned
        if not os.path.exists(name):
            print("Cloning {} from {}".format(name, clone_link))
            gitutil.clone_from(obj, clone_link, name)
        else:
            print("Found directory with matching name {}".format(name))

    print("Done")


class OrgContext:
    def __init__(self, config, organization):
        self.config = config
        self.organization = organization


@cli.group("organization", invoke_without_command=True)
@click.argument("organization_name", type=str)
@click.pass_context
def organization(ctx, organization_name):
    """Execute operation on a target organization"""
    ctx.obj: config.Config
    c = ctx.obj.get_gitlab_client()

    g = c.groups.get(organization_name)

    logger.bind(group_name=g.attributes["name"]).debug("Found organization")
    ctx.obj = OrgContext(ctx.obj, g)


@organization.command("clone")
@click.argument("output_dir", type=str)
@click.pass_obj
def clone(obj: OrgContext, output_dir: str):
    """Clone an entire organization into the given directory"""
    log = logger.bind(organization_name=obj.organization.attributes["name"], output_dir=output_dir)
    log.info("Cloning organization")

    log.debug("Creating output directory")
    os.makedirs(output_dir, exist_ok=True)

    pids = [
        (p.attributes["path"], p.attributes["http_url_to_repo"])
        for p in obj.organization.projects.list(all=True)
    ]

    log.bind(num_repos=len(pids)).info("Found repositories to clone")

    for name, clone_link in pids:
        rlog = log.bind(repo_name=name)
        clone_path = os.path.join(output_dir, name)
        rlog.bind(clone_path=clone_path).debug("Check the repo isn't already cloned")
        if not os.path.exists(clone_path):
            rlog.bind(clone_link=clone_link).info("Cloning repository into output dir")

            gitutil.clone_from(obj.config, clone_link, clone_path)
        else:
            rlog.info("Found a directory with a name matching the derived repository name")

    log.info("Finished organization clone")


class RepoContext:
    def __init__(self, config, organization, repos):
        self.config = config
        self.organization = organization
        self.repos = repos


@organization.group("repos", invoke_without_command=True)
@click.argument("repo_regex", type=clitypes.Regex())
@click.pass_context
def repos(ctx, repo_regex):
    """operate on sets of repos"""
    ctx.obj: OrgContext

    projects = [
        (p, repo_regex.match(p.attributes["name"]))
        for p in ctx.obj.organization.projects.list(all=True)
        if repo_regex.match(p.attributes["name"]) is not None
    ]

    for p, _ in projects:
        logger.bind(repo_name=p.attributes["name"]).debug("Found repository")

    if len(projects) > 0:
        logger.bind(num_repos=len(projects)).info("Matched repositories.")
    else:
        logger.error("No repos matched for regex: {}".format(repo_regex))

    ctx.obj = RepoContext(ctx.obj.config, ctx.obj.organization, projects)


@repos.command("list")
@click.option("--format", default="list", type=click.Choice(["list", "json", "yaml"]))
@click.pass_obj
def list_repos(obj: RepoContext, format: str):
    """list the selected repos"""
    if format == "list":
        for r, _ in obj.repos:
            print(r.attributes["name"])
    elif format == "json":
        print(json.dumps([r.attributes for r, _ in obj.repos], indent=2, sort_keys=True))
    elif format == "yaml":
        print(yaml.round_trip_dump([r.attributes for r, _ in obj.repos]))
    else:
        raise NotImplementedError("format={} is not implemented.".format(format))


class RepoMirrorContext:
    def __init__(self, config, organization, repos):
        self.config = config
        self.organization = organization
        self.repos = repos


@repos.group("mirrors")
# @click.option("--format", default="list", type=click.Choice(["list", "json", "yaml"]))
@click.pass_context
def mirrors(ctx):
    """access the mirroring configuration via the Gitlab UI client (slow)"""
    ctx.obj: RepoContext
    ctx.obj = RepoMirrorContext(ctx.obj.config, ctx.obj.organization, ctx.obj.repos)


@mirrors.command("list")
@click.pass_obj
def list_mirrors(obj: RepoMirrorContext):
    """list the currently configured mirrors for the repository"""

    logger.debug("Constructing Gitlab User Interface client...")
    uic = GitlabUIClient(
        obj.config.gitlab_server,
        obj.config.user,
        obj.config.user_password.unmasked(),
        obj.config.otp_secret.unmasked(),
    )
    logger.debug("Gitlab UI client ready.")

    for p, _ in obj.repos:
        uic.list_repository_mirrors(p.attributes["path_with_namespace"])

    pass


@repos.command("delete")
@click.option(
    "--doit/--dryrun",
    default=False,
    help="Whether to actually delete repositories",
    show_default=True,
)
@click.option(
    "--seriously/--no-just-kidding",
    default=False,
    help="Whether to actually delete repositories",
    show_default=True,
)
@click.option(
    "--quiet/--verbose",
    default=False,
    help="Print list of repos to delete to stdout",
    show_default=True,
)
@click.pass_obj
def delete_repos(obj: RepoContext, doit: bool, seriously: bool, quiet: bool):
    """mass delete repositories in an organization according to a regex"""
    for r, _ in obj.repos:
        if not quiet:
            print(r.attributes["name"])
        project_name = r.attributes["name"]
        if doit and seriously:
            logger.bind(project_name=project_name).debug("Looking up actual project")
            c = obj.config.client
            prj = c.projects.get(r.attributes["id"])
            logger.bind(project_name=project_name).info("Deleting project")
            prj.delete()
            logger.bind(project_name=project_name).debug("Deleted project")
        else:
            logger.bind(project_name=project_name).info("DRY RUN - NO ACTION")


def main():
    cli()


if __name__ == "__main__":
    main()
