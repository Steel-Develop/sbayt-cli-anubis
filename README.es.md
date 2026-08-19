# Anubis CLI

Anubis ofrece una interfaz pequeña para preparar herramientas locales y operar
infraestructura Kubernetes. Delega en las herramientas nativas y no sustituye
a Terraform, Ansible, Helmfile ni kubectl.

[Read in English](README.md)

## Instalación

Requiere Python 3.12 o superior:

```bash
uv tool install anubis-cli
# o
pipx install anubis-cli
```

`anubis --help` muestra la interfaz disponible.

Activa el autocompletado una vez después de instalar:

```bash
# zsh
anubis --print-completion-script zsh > ~/.anubis-completion.zsh
echo 'source ~/.anubis-completion.zsh' >> ~/.zshrc

# bash
anubis --print-completion-script bash > ~/.anubis-completion.bash
echo 'source ~/.anubis-completion.bash' >> ~/.bashrc
```

Abre una terminal nueva o carga el fichero generado para activarlo al momento.

## Flujo Kubernetes

Desde un repositorio IaC compatible:

```bash
anubis install internal/local
anubis stop
anubis start
anubis update
anubis destroy --yes
```

`install` prepara el clúster y despliega el producto. Los comandos individuales
permiten ejecutar una sola etapa. Las operaciones avanzadas del clúster están
agrupadas en `anubis cluster`.

La instalación se puede indicar por nombre lógico, directorio o ruta al
`installation.yaml`. Anubis recuerda la última selección explícita en el
fichero ignorado `.work/anubis/active-installation` del repositorio, por lo que
los comandos posteriores pueden omitirla. Indicar otra instalación cambia la
selección activa. Solo hace falta `--repository RUTA` cuando Anubis no puede
descubrir el repositorio desde el directorio actual.

`stop` escala a cero los procesos del producto pero mantiene disponibles las
bases de datos, Kafka, los operadores y los volúmenes. `start`, `deploy` o
`update` recuperan las réplicas declaradas. `destroy --yes` elimina de forma
irreversible el producto y sus datos Kubernetes, conservando el clúster;
`cluster destroy --yes` elimina además un clúster Kind o Terraform/libvirt
gestionado.

`deploy` fuerza la reconciliación de todas las releases y resulta útil para un
primer despliegue o para corregir cambios manuales en el clúster. `update` es la
operación habitual de mantenimiento: muestra el diff y aplica únicamente las
releases cuya configuración declarada ha cambiado.

### Configuración opcional del repositorio

Un repositorio puede incluir un `anubis.yaml` opcional con configuración
compartida no secreta. Por ejemplo, los bindings de Bitwarden relacionan rutas
del manifiesto con claves del proyecto seleccionado durante la ejecución:

```yaml
bitwarden:
  bindings:
    data.mongodb.username: MONGO_INITDB_ROOT_USERNAME
```

El fichero no es obligatorio: una instalación completa funciona sin él. Los
valores personales de AWS y CodeArtifact también se pueden guardar mediante
`anubis config init` en `~/.config/anubis/config.toml`.

El token se pasa con `BWS_ACCESS_TOKEN` o mediante el prompt oculto. Ni tokens
ni contraseñas se escriben en la configuración o el repositorio. El contexto
local queda en el directorio ignorado `.work/anubis/` del IaC.

## Herramientas de desarrollo conservadas

```bash
anubis bitwarden install
anubis bitwarden remove
anubis aws install
anubis aws configure-pip
anubis aws configure-uv
anubis aws token
anubis check environment
```

La configuración AWS procede de opciones, variables `ANUBIS_*`, configuración
opcional del repositorio o configuración personal. Las credenciales se leen
del entorno estándar o del proyecto Bitwarden seleccionado.
`anubis aws configure-uv` reemplaza `~/.config/uv/uv.toml`; `anubis aws reset`
elimina posteriormente ese fichero gestionado por Anubis.

## Desarrollo

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run anubis --help
uv build
```

El paquete solo usa dependencias públicas de PyPI. Los artefactos no deben
contener manifests de despliegue, credenciales ni configuración privada.
