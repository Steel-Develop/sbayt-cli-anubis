import importlib.metadata

from invoke import Collection, Program

from anubis.tasks import airflow, aws, bitwarden, check, docker, misc

ns = Collection()
ns.add_collection(aws.aws_ns)
ns.add_collection(bitwarden.bws_ns)
ns.add_collection(docker.docker_ns)
ns.add_collection(check.check_ns)
ns.add_collection(airflow.airflow_ns)

ns.add_task(misc.version, name="version")
ns.add_task(misc.help, default=True)
ns.add_task(misc.install_global_config, name="install-global-config")

program = Program(
    namespace=ns,
    version=importlib.metadata.version("anubis-cli"),
)
