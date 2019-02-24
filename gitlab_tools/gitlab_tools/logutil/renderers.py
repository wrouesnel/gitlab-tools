# coding: utf-8
"Color key value renderer"

import itertools
from io import StringIO

import colorama
import structlog

LEVEL_COLORS = {
    "critical": colorama.Fore.RED,
    "exception": colorama.Fore.RED,
    "error": colorama.Fore.RED,
    "warn": colorama.Fore.YELLOW,
    "warning": colorama.Fore.YELLOW,
    "info": colorama.Fore.GREEN,
    "debug": colorama.Fore.WHITE,
    "notset": colorama.Back.RED,
}

COLORS = {
    "timestamp": colorama.Style.DIM,
    "time": colorama.Style.DIM,
    "event": colorama.Fore.CYAN + colorama.Style.BRIGHT,
}

# all ANSI colors, except black, white and cyan
KV_COLORS = (
    colorama.Fore.RED,
    colorama.Fore.GREEN,
    colorama.Fore.YELLOW,
    colorama.Fore.BLUE,
    colorama.Fore.MAGENTA,
)


def _color(key, colors):
    return COLORS.get(key, next(colors))


class ColorKeyValueRenderer(structlog.processors.KeyValueRenderer):
    "Renderer to output key values with colors"

    def __init__(self, force_colors=False, **kwargs):
        super().__init__(self, **kwargs)

        if force_colors:
            colorama.deinit()
            colorama.init(strip=False)
        else:
            colorama.init()

    def __call__(self, _, __, event_dict):
        colors_iterator = itertools.cycle(reversed(KV_COLORS))
        buffer = StringIO()

        level_color = None
        if "level" in event_dict:
            level_color = LEVEL_COLORS[event_dict["level"]]

        for key, value in self._ordered_items(event_dict):
            if value is not None:
                if key == "event" and level_color is not None:
                    buffer.write(
                        level_color + key + "=" + str(value) + colorama.Style.RESET_ALL + " "
                    )
                else:
                    buffer.write(
                        _color(key, colors_iterator)
                        + key
                        + "="
                        + self._repr(value)
                        + colorama.Style.RESET_ALL
                        + " "
                    )

        return buffer.getvalue()
