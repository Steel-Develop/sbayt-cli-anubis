from invoke import Collection, Exit, task

from anubis.utils import DEFAULT_ENV, deploy_spark_dags, remove_spark_dags


@task
def deploy_dags(ctx, load_secrets_from_bws=None, deployment_file=None, env=DEFAULT_ENV):
    """
    Deployment of Airflow Dags and integration with the platform. Downloads
        files from CodeArtifact, renders the dags (if variable injection is
        needed), and distributes the files to their corresponding paths on the
        platform.

    Raises:
        Exit: If the DAG or job folder doesn't exist in the subdirectories or
            if aws cli is not installed.

    Usage:
        anubis spark.deploy-dags
    """
    success = deploy_spark_dags(
        load_secrets_from_bws=load_secrets_from_bws,
        deployment_file=deployment_file,
        env=env,
    )

    if not success:
        raise Exit(code=1)


@task
def remove_dags(ctx, deployment_file=None, env=DEFAULT_ENV):
    """
    Deletion of job and dag files and restoration of the folder structure.

    Raises:
        Exit: If the DAG or job folder doesn't exist in the subdirectories.

    Usage:
        anubis spark.remove-dags
    """
    success = remove_spark_dags(deployment_file=deployment_file, env=env)

    if not success:
        raise Exit(code=1)


airflow_ns = Collection("airflow")
airflow_ns.add_task(deploy_dags)
airflow_ns.add_task(remove_dags)
