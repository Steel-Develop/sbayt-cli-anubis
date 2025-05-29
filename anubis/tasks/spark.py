import os
import logging
import shutil
from pathlib import Path

from invoke import task, Exit, Collection

from anubis.utils import (
    DEFAULT_DEPLOYMENT_FILE,
    LOAD_SECRETS_FROM_BWS_NAME,
    DOCKER_COMPOSE_CMD,
    DEFAULT_ENV,
    DEFAULT_DAGS_PATH,
    DEFAULT_JOBS_PATH,
    _ensure_tool_installed,
    _install_aws_cli,
    _get_cached_config,
    _load_secrets_from_bws,
    _get_zip_from_codeartifact,
    _unzip_artifact,
    _render_dag_template,
    _deploy_job_and_dag_files,
    _remove_job_and_dag_files,
    _get_env_file
)


@task
def deploy_jobs(ctx, load_secrets_from_bws=None, deployment_file=None,
                env=DEFAULT_ENV):
    """
    Deployment of Spark jobs and Airflow dags and integration with the
        platform. Downloads files from CodeArtifact, renders the dags (if
        variable injection is needed), and distributes the files to their
        corresponding paths on the platform.
        
    Raises:
        Exit: If the DAG or job folder doesn't exist in the subdirectories or 
            if aws cli is not installed.
        
    Usage:
        anubis spark.deploy-jobs
    """
    config = _get_cached_config(
        path=deployment_file or DEFAULT_DEPLOYMENT_FILE
    )
    
    dags_path = Path(config.get('dags_path', DEFAULT_DAGS_PATH))
    jobs_path = Path(config.get('jobs_path', DEFAULT_JOBS_PATH))
    
    if not dags_path.exists():
        logging.error(f'x DAGs path does not exists. Path: {dags_path}')
        raise Exit(code=1)
    if not jobs_path.exists():
        logging.error(f'x Jobs path does not exists. Path: {jobs_path}')
        raise Exit(code=1)
    
    # Check AWS CLI installed
    if not _ensure_tool_installed("aws", _install_aws_cli):
        raise Exit(code=1)

    load_secrets = (
        load_secrets_from_bws
        if load_secrets_from_bws is not None
        else config.get(LOAD_SECRETS_FROM_BWS_NAME, True)
    )

    bws_secrets = {}
    if load_secrets:
        # Load secrets from Bitwarden
        bws_secrets = _load_secrets_from_bws(deployment_file)
        if not bws_secrets:
            logging.warning("⚠️ No secrets found in Bitwarden.")

    # Validate jobs configuration
    dags_config = config.get('airflow_dags')
    if not dags_config:
        logging.warning(
            "x Spark jobs config not found or empty. "
            "Add jobs config to 'spark_jobs:' in your deployment.yml"
        )
        return
    

    tmp_dir = Path.home() / 'spark_jobs'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    for package_name, params in dags_config.items():
        artifact_path = tmp_dir / package_name
        
        _get_zip_from_codeartifact(
            package_name=package_name,
            version=params['version'],
            artifact_path=artifact_path,
            bws_secrets=bws_secrets,
            deployment_file=deployment_file
            )
        
        _unzip_artifact(artifact_path=artifact_path)
        
        _render_dag_template(artifact_path=artifact_path, **params)
        
        _deploy_job_and_dag_files(
            artifact_path=artifact_path,
            dags_path=dags_path,
            jobs_path=jobs_path
        )
        
    shutil.rmtree(tmp_dir)
    
    # Restart services
    env_file = _get_env_file(env)
    
    docker_info = ctx.run(
        f'{DOCKER_COMPOSE_CMD} --env-file {env_file} ps --status running --quiet',
        hide=True,
        warn=True
    )
    # Comprobación de si hay contenedores corriendo para reinicio de servicios
    if any(line.strip() for line in docker_info.stdout.splitlines()):
        logging.info("Restarting Apache Livy...")
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} down apache_livy',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} up apache_livy -d',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        
        logging.info("Restarting Airflow Scheduler")
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} down airflow-scheduler',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} up airflow-scheduler -d',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
    
@task
def remove_jobs(ctx, deployment_file=None, env=DEFAULT_ENV):
    """
    Deletion of job and dag files and restoration of the folder structure.
    
    Raises:
        Exit: If the DAG or job folder doesn't exist in the subdirectories.
    
    Usage:
        anubis spark.remove-jobs
    """
    
    config = _get_cached_config(
        path=deployment_file or DEFAULT_DEPLOYMENT_FILE
    )
    dags_path = Path(config.get('dags_path', DEFAULT_DAGS_PATH))
    jobs_path = Path(config.get('jobs_path', DEFAULT_JOBS_PATH))
    
    if not dags_path.exists():
        logging.error(f'x DAGs path does not exists. Path: {dags_path}')
        raise Exit(code=1)
    if not jobs_path.exists():
        logging.error(f'x Jobs path does not exists. Path: {jobs_path}')
        raise Exit(code=1)
        
    
    _remove_job_and_dag_files(dags_path=dags_path, jobs_path=jobs_path)
    
    # Restart services
    env_file = _get_env_file(env)
    
    docker_info = ctx.run(
        f'{DOCKER_COMPOSE_CMD} --env-file {env_file} ps --status running --quiet',
        hide=True,
        warn=True
    )
    # Comprobación de si hay contenedores corriendo para reinicio de servicios
    if any(line.strip() for line in docker_info.stdout.splitlines()):
        logging.info("Restarting Apache Livy...")
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} down apache_livy',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} up apache_livy -d',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        
        logging.info("Restarting Airflow Scheduler")
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} down airflow-scheduler',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        ctx.run(
            f'{DOCKER_COMPOSE_CMD} --env-file {env_file} up airflow-scheduler -d',
            env={**os.environ, "ENV": env},
            hide=True,
            pty=False,
        )
        


spark_ns = Collection('spark')
spark_ns.add_task(deploy_jobs)
spark_ns.add_task(remove_jobs)