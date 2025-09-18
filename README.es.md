<h1 align="center">𓁢 Anubis CLI</h1>

<p align="center">
    <em>Servicio Automatizado de Instalación de Red y Base de Usuarios</em>
</p>

<p align="center">
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/v/anubis-cli?color=%2334D058&label=pypi%20package" alt="Versión del paquete">
</a>
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/anubis-cli.svg?color=%2334D058" alt="Versiones de Python soportadas">
</a>
</p>

---

📖 Leer en otros idiomas:
- [English](./README.md)

---

## Descripción

Esta herramienta define y organiza un conjunto de tareas automatizadas para configurar y
gestionar entornos de desarrollo/producción. Utiliza `invoke` para estructurar las tareas
y `rich` para mejorar la experiencia en terminal.

### Características principales

- Instalación local y gestión de herramientas CLI esenciales (AWS CLI, Bitwarden CLI).
- Configuración de repositorios privados (CodeArtifact) para `pip` y `uv`.
- Automatización de servicios Docker (`create network`, `start`, `stop`, `clean`, `build`).
- Verificación de configuraciones de seguridad y entorno local (Bitwarden, AWS ECR, etc.).

## Instalación y Uso Básico

### Requisitos

- [Python](https://www.python.org/downloads/) >= 3.10
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) >= 0.7.0
- Un archivo de despliegue (local o global, por defecto: deployment.yml) para definir perfiles y credenciales.

### Instalación global

Para instalar la herramienta de forma global, puedes utilizar `uv`(**recomendado**) o `pipx`.

```bash
# Con uv (recomendado)
uv tool install anubis-cli
```

```bash
# Con pipx
pipx install anubis-cli
```

### Uso básico

 1. Ver tareas disponibles:

```bash
anubis help
```

 2. Verificar tu entorno local:

```bash
anubis check.environment
```

 3. Iniciar servicios Docker con perfiles específicos:

```bash
anubis docker.up --profiles=infra,api --env=prod
```

 4. Configurar pip para CodeArtifact:
 
```bash
anubis aws.configure-pip
```


Configurar autocompletado para `anubis`:

```bash
# Para bash
anubis --print-completion-script bash > ~/.anubis-completion.bash
echo "source ~/.anubis-completion.bash" >> ~/.bashrc
source ~/.bashrc

# Para zsh
anubis --print-completion-script zsh > ~/.anubis-completion.zsh
echo "source ~/.anubis-completion.zsh" >> ~/.zshrc
source ~/.zshrc
```

Para más detalles o ejemplos adicionales, consulta la documentación de cada tarea
usando el comando `anubis --list` o revisa los docstrings individuales.

## Configuración del Entorno de Desarrollo

### Requisitos

- [Python](https://www.python.org/downloads/) >= 3.10
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) >= 0.7.0

### Configuración

1. Crea el entorno virtual:

```bash
uv sync
```

2. Comprobar que el entorno virtual se ha creado correctamente:

```bash
uv pip check
uv tree
```

3. Utiliza el entorno virtual:

   Al utilizar `uv` como gestor de paquetes, podemos utilizar el entorno de varias maneras:

   - (**Recomendado**) Utilizar el comando `uv run <comando>` para ejecutar comandos dentro del entorno virtual:

```bash
uv run anubis
uv run pytest -m unit
```

   - Activar el entorno virtual:

```bash
   source .venv/bin/activate
```

## Manejo de Dependencias

Al utilizar `uv` como gestor de paquetes, podemos manejar las dependencias de nuestro proyecto de manera sencilla. Cuando se instala una dependencia, se guarda en el archivo `uv.lock` para que se pueda reproducir el entorno en otro lugar, además de añadirlo al archivo `pyproject.toml` en su sección correspondiente.

- Para instalar nuevas dependencias o actualizar una existente, simplemente ejecuta el siguiente comando:

```bash
uv add <package>
```

- Para añadir las dependencias de desarrollo, ejecuta el siguiente comando:

```bash
uv add --dev <package>
```

- Para eliminar una dependencia, ejecuta el siguiente comando:

```bash
uv remove <package>
uv remove --dev <package>
```

- También se pueden exportar las dependencias a un archivo `requirements.txt`:

```bash
uv export --no-hashes -o requirements.txt
```

## Creación de un nuevo paquete

1. Ejecuta el siguiente comando para crear un nuevo paquete:

```bash
uv build
```

2. Se creará la carpeta `dist` con el paquete y su _wheel_.

3. Instala el paquete en tu entorno virtual en otro proyecto:

```bash
uv tool install --from dist/anubis_cli-{version}-py3-none-any.whl anubis-cli
```

## Cómo Contribuir

Para una guía completa sobre cómo contribuir al proyecto, revisa la [Contribution Guide](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/CONTRIBUTING.md).

### Reportar Incidencias

If you believe you've found a defect in this project or its documentation, open an issue in [Jira](https://steeldevelop.atlassian.net/) so we can address it.

If you're unsure whether it's a bug, feel free to discuss it in our forums or internal chat—someone will be happy to help.

## Código de Conducta

Consulta el [Código de Conducta](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/code-of-conduct.md).

## Licencia

Consulta el archivo [LICENSE](./LICENSE).
