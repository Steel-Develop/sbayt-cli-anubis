# Sbayt - Python Package Template

Template de proyecto para paquetes de Python.

## Estructura del Proyecto

```bash
sbayt-pyp-template
├── code_of_conduct.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml
├── src
│   ├── README.md
│   ├── __init__.py
│   └── hello_world.py
├── tests
│   ├── conftest.py
│   └── test_hello_world.py
└── uv.lock
```

## Configuración del Entorno de Desarrollo

A continuación se indica cómo preparar el entorno de desarrollo.

### Requisitos

- [Python](https://www.python.org/downloads/) >= 3.9
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) >= 0.4.30

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
     uv run python src/hello_world.py
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
   uv pip install dist/sbayt_pyp_template-<version>-py3-none-any.whl
   ```

   o simplemente (sin uv):

   ```bash
    pip install dist/sbayt_pyp_template-<version>-py3-none-any.whl
   ```

## Despliegue del Paquete

Al ejecutar el _workflow_ [CI.yml](.github/workflows/CI.yml), se desplegará el paquete en el **CodeArtifact** de AWS.

> **Nota:** Se debe tener en cuenta que los comandos que cambian el índice de _pip_ hacen que la herramienta pase a utilizar ese índice, por lo que es necesario volver a configurar el índice de _pip_ si se desea instalar paquetes de otros repositorios.
> <br>**Se recomienda desplegar el paquete mediante GitHub Actions para evitar problemas.** En desarrollo se puede optar por instalar el paquete localmente.

Para utilizar el paquete de **CodeArtifact** en otro proyecto, sigue los siguientes pasos:

1. Configura el acceso a **CodeArtifact** en tu entorno local:

   ```bash
   aws configure
   ```

2. Configura el instalador de paquetes de Python para que utilice **CodeArtifact**:

- Si utilizas `pip`, existen dos opciones:

  - Ejecutar el siguiente comando de _AWS CLI_ para configurar el índice de _pip_:

  ```bash
  aws codeartifact login --tool pip --repository python-sbayt-repository --domain sbayt --domain-owner 865413084983 --region eu-west-1
  ```

  - Extraer el token de autorización y configurar mediante `pip config` (**cambiando el índice**) o por parámetro (**sin cambiar el índice**):

  ```bash
  export CODEARTIFACT_AUTH_TOKEN=`aws codeartifact get-authorization-token --domain sbayt --domain-owner 865413084983 --region eu-west-1 --query authorizationToken --output text`

  # Si se utiliza `pip config`:

  pip config set global.index-url https://aws:$CODEARTIFACT_AUTH_TOKEN@sbayt-865413084983.d.codeartifact.eu-west-1.amazonaws.com/pypi/python-sbayt-repository/simple/

  pip install <package>

  # Si se hace por parámetro:

  pip install <package> --index-url https://aws:$CODEARTIFACT_AUTH_TOKEN@sbayt-865413084983.d.codeartifact.eu-west-1.amazonaws.com/pypi/python-sbayt-repository/simple/
  ```

- Si utilizas `uv`, es necesario configurar las variables de entorno o utilizar los parámetros:

  ```bash
  export CODEARTIFACT_AUTH_TOKEN=`aws codeartifact get-authorization-token --domain sbayt --domain-owner 865413084983 --region eu-west-1 --query authorizationToken --output text`

  # Si se establece la variable de entorno

  export UV_DEFAULT_INDEX=`https://aws:$CODEARTIFACT_AUTH_TOKEN@sbayt-865413084983.d.codeartifact.eu-west-1.amazonaws.com/pypi/python-sbayt-repository/simple/`

  uv add <package>

  # Si se utiliza el parámetro

  uv add <package> --default-index https://aws:$CODEARTIFACT_AUTH_TOKEN@sbayt-865413084983.d.codeartifact.eu-west-1.amazonaws.com/pypi/python-sbayt-repository/simple/
  ```

- También existe la posibilidad de añadir la cabecera al inicio del fichero `requirements.txt`:

  ```bash
  echo "$(echo '--extra-index-url https://aws:'"$CODEARTIFACT_AUTH_TOKEN"'@sbayt-865413084983.d.codeartifact.eu-west-1.amazonaws.com/pypi/python-sbayt-repository/simple/' | cat - requirements.txt)" > requirements.txt
  ```

  Tras esto ya se podrán instalar las dependencias del proyecto con `pip install -r requirements.txt` o `uv pip install -r requirements.txt`.

## GitHub Actions

El archivo [CI.yml](.github/workflows/CI.yml) contiene un flujo de trabajo que se ejecuta en cada push a la rama master. Este flujo de trabajo consta de los siguientes trabajos:

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
- Configura las credenciales de **AWS**.
- Configura `uv`.
- Construye y publica el paquete a **CodeArtifact**.

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

## License

See the [LICENSE](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/LICENSE) file.
