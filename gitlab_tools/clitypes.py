"""Implements custom click command line types"""

import re

import click


class Regex(click.ParamType):
    name = "regex"

    def convert(self, value, param, ctx):
        try:
            return re.compile(value)
        except Exception as e:
            self.fail("{} cannot be compiled as a regex: {}".format(value, str(e)))
