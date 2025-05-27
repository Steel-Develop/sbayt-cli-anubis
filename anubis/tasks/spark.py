import os

import logging
import shutil
from pathlib import Path
from invoke import task, Exit, Collection

from anubis.utils import (
    DEFAULT_DEPLOYMENT_FILE,
    LOAD_SECRETS_FROM_BWS_NAME,
    DOCKER_COMPOSE_CMD,
    _ensure_tool_installed,
    _install_aws_cli,
    _get_cached_config,
    _load_secrets_from_bws,
    _get_zip_from_codeartifact,
    _unzip_job,
    _render_dag_template,
    _deploy_job_and_dag_files,
    _remove_job_and_dag_files,
    DEFAULT_ENV,
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
        
    Usage:
        anubis spark.deploy-jobs
    """
    
    
    # Check AWS CLI installed
    if not _ensure_tool_installed("aws", _install_aws_cli):
        raise Exit(code=1)

    config = _get_cached_config(
        path=deployment_file or DEFAULT_DEPLOYMENT_FILE
    )

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
    jobs_config = config.get('spark_jobs')
    if not jobs_config:
        logging.warning(
            "x Spark jobs config not found or empty. "
            "Add jobs config to 'spark_jobs:' in your deployment.yml"
        )
        return
    
    tmp_dir = Path.home() / 'spark_jobs'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    for package_name, params in jobs_config.items():
        job_folder_path = tmp_dir / package_name
        
        _get_zip_from_codeartifact(
            package_name=package_name,
            version=params['version'],
            job_folder_path=job_folder_path,
            bws_secrets=bws_secrets,
            deployment_file=deployment_file
            )
        
        _unzip_job(job_folder_path=job_folder_path)
        
        _render_dag_template(job_folder_path=job_folder_path, **params)
        
        _deploy_job_and_dag_files(job_folder_path=job_folder_path)
        
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
def remove_jobs(ctx, env=DEFAULT_ENV):
    """
    Deletion of job and dag files and restoration of the folder structure.
    
    Usage:
        anubis spark.remove-jobs
    """
    
    _remove_job_and_dag_files()
    
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