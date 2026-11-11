"""Command modules.

Each module exposes ``COMMANDS: dict[str, Callable[[argparse.Namespace], int]]``
and, optionally, a ``configure(parser)`` function that adds its own flags.
``marge.cli`` discovers them at start-up: never edit the dispatcher to add a
command, add a module here instead.
"""
