"""relay: a small, generic harness for model-driven software work.

The core loop is the same whoever carries the messages: send the model a turn,
receive tool requests, run the permitted ones, return the results. A *driver*
decides how a turn reaches the model (a person pasting into a browser, a CLI,
an API). *Tools* are what the model may ask for. *Policy* says what is allowed.
Every turn and tool call is written to a trace.

Standard library only; Python 3.9+.
"""

__version__ = "0.2.0"
