from invoke import Collection

from seshat.tasks import aws
from seshat.utils import help, version

ns = Collection()
ns.add_collection(aws.aws_ns)


ns.add_task(version, name="version")
ns.add_task(help, default=True)
