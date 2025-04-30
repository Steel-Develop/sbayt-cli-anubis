import importlib.metadata

from invoke import Collection, Program

from seshat import tasks

program = Program(
    namespace=Collection.from_module(tasks),
    version=importlib.metadata.version("seshat-cli"),
)
