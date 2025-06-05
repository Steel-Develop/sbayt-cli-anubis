<h1 align="center">𓁢 Anubis CLI</h1>

<p align="center">
    <em>Automated Network & User Base Installation Service</em>
</p>

<p align="center">
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/v/anubis-cli?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/anubis-cli.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

## Descripción

Esta herramienta define y organiza un conjunto de tareas automatizadas para configurar y
gestionar entornos de desarrollo/producción. Utiliza `invoke` para estructurar las tareas
y `rich` para mejorar la experiencia en terminal.

### Características principales

- Instalación local y gestión de herramientas CLI esenciales (AWS CLI, Bitwarden CLI).
- Configuración de repositorios privados (CodeArtifact) para pip y uv.
- Automatización de servicios Docker (crear red, iniciar, detener, limpiar, construir).
- Verificación de configuraciones de seguridad y entorno local (Bitwarden, AWS ECR, etc.).

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

### Requisitos

- Python 3.9 o superior.
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) para instalar herramientas globalmente.
- Un archivo de despliegue (local o global, por defecto: deployment.yml) para definir perfiles y credenciales.

### Uso básico

   1. Ver tareas disponibles:
        `anubis help`
   2. Verificar tu entorno local:
        `anubis check.environment`
   3. Iniciar servicios Docker con perfiles específicos:
        `anubis docker.up --profiles=infra,api --env=prod`
   4. Configurar pip para CodeArtifact:
        `anubis aws.configure-pip`

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

A continuación se indica cómo preparar el entorno de desarrollo.

### Requisitos

- [Python](https://www.python.org/downloads/) >= 3.9
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

   - (**Recomendado**) Utilizar el comando `un run <comando>` para ejecutar comandos dentro del entorno virtual:

     ```bash
     uv run anubis
     uv run pytest -m unit
     ```

   - Activar el entorno virtual:

     ```bash
        source .venv/bin/activate
     ```

### Manejo de Dependencias

Al utilizar `uv` como gestor de paquetes, podemos manejar las dependencias de nuestro proyecto de manera sencilla. Cuando se instala una dependencia, se guarda en el archivo `uv.lock` para que se pueda reproducir el entorno en otro lugar, además de añadirlo al archivo `pyproject.toml` en su sección correspondiente.

Para instalar nuevas dependencias o actualizar una existente, simplemente ejecuta el siguiente comando:

```bash
uv add <package>
```

Para añadir las dependencias de desarrollo, ejecuta el siguiente comando:

```bash
uv add --dev <package>
```

Para eliminar una dependencia, ejecuta el siguiente comando:

```bash
uv remove <package>
uv remove --dev <package>
```

También se pueden exportar las dependencias a un archivo `requirements.txt`:

```bash
uv export --no-hashes -o requirements.txt
```

## Creación de un nuevo paquete

Para crear un nuevo paquete en desarrollo, sigue los siguientes pasos:

1. Ejecuta el siguiente comando para crear un nuevo paquete:

   ```bash
   uv build
   ```

2. Se creará la carpeta `dist`con el paquete y su _wheel_.

3. Instala el paquete en tu entorno virtual en otro proyecto:

   Mueve la carpeta `dist` al directorio raíz del proyecto y ejecuta el siguiente comando:

   ```bash
   uv tool install --from dist/anubis_cli-{version}-py3-none-any.whl anubis-cli

   ```

## Despliegue del Paquete

Al ejecutar el _workflow_ [CI.yml](.github/workflows/CI.yml), se desplegará el paquete en **PyPI**.

## GitHub Actions

El archivo [ci.yml](.github/workflows/ci.yml) contiene un flujo de trabajo que se ejecuta en cada push a la rama master. Este flujo de trabajo consta de los siguientes trabajos:

### fetch

Realiza la acción de checkout del código fuente desde el repositorio.

### lint

Realiza las siguientes acciones:

- Checkout del código fuente.
- Configura Python utilizando la acción setup-python.
- Configura `uv`.
- Sincroniza las dependencias utilizando `uv`.
- Verifica los paquetes instalados.
- Ejecuta los hooks de pre-commit para asegurar la calidad del código.

### test

Utiliza una estrategia de matriz para probar en múltiples versiones de Python (3.10, 3.11, 3.12).

Realiza las siguientes acciones:

- Checkout del código fuente.
- Configura Python utilizando la acción setup-python.
- Configura `uv`.
- Sincroniza las dependencias utilizando `uv`.
- Ejecuta las pruebas unitarias utilizando `pytest`.
- Ejecuta las pruebas de integración utilizando `pytest`.

### scan

Realiza las siguientes acciones:

- Checkout del código fuente.
- Ejecuta el escáner de vulnerabilidades **Trivy** en modo repositorio para buscar vulnerabilidades críticas y altas en el código, secretos y configuraciones.

### publish

Realiza las siguientes acciones:

- Checkout del código fuente.
- Configura Python utilizando la acción setup-python.
- Configura `uv`.
- Construye y publica el paquete a **PyPI**.

## Ejecución de los Tests

Si deseas ejecutar todos los tests (unitarios y de integración) en el directorio tests, simplemente puedes ejecutar `pytest` sin especificar un directorio:

```bash
uv run pytest
```

Esto ejecutará todos los tests que `pytest` pueda encontrar en el directorio actual y sus subdirectorios.

### Ejecución de Tests Unitarios

Para ejecutar solo los tests unitarios, que estarían organizados en el directorio `tests/unit`:

```bash
uv run pytest tests/unit
```

Esto ejecutará todos los tests unitarios que se encuentren en ese directorio y sus subdirectorios.

También puedes especificar un archivo específico si solo deseas ejecutar los tests de un archivo particular:

```bash
uv run pytest tests/unit/test_module1.py
```

### Ejecución de Tests de Integración

Para ejecutar solo los tests de integración, que estarían organizados en el directorio `tests/integration`:

```bash
uv run pytest tests/integration
```

Esto ejecutará todos los tests de integración que se encuentren en ese directorio y sus subdirectorios.

Al igual que con los tests unitarios, puedes especificar un archivo específico si solo deseas ejecutar los tests de un archivo particular:

```bash
uv run pytest tests/integration/test_integration_module1.py
```

### Marcadores o Tags

Además, `pytest` permite usar marcadores o tags para categorizar tus tests y ejecutar solo aquellos marcados con un cierto `tag`.

Esto es útil si quieres ejecutar un grupo específico de tests independientemente de su ubicación en el directorio.

Por ejemplo, si tienes marcadores como `@pytest.mark.unit` y `@pytest.mark.integration`, puedes ejecutar solo los tests marcados como unitarios o de integración de esta manera:

```bash
uv run pytest -m unit  # Ejecuta solo tests marcados como unit
uv run pytest -m integration  # Ejecuta solo tests marcados como integration
```

## Contributing

For a complete guide on how to contribute to the project, please review the [Contribution Guide](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/CONTRIBUTING.md).

### Reporting Issues

If you believe you've found a defect in this project or its documentation, open an issue in [Jira](https://steeldevelop.atlassian.net/) so we can address it.

If you're unsure whether it's a bug, feel free to discuss it in our forums or internal chat—someone will be happy to help.

## Code of Conduct

See the [Code of Conduct](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/code-of-conduct.md).
