#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#
import argparse
import itertools
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

from invoke import Context

from ci_common_utils import Logger

LOGGER = Logger()

CURRENT_DIR = Path(os.getcwd())
ROOT_DIR = Path(os.getcwd())
while str(ROOT_DIR) != "/" and not (ROOT_DIR / "pyproject.toml").is_file():
    ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) == "/":
    LOGGER.critical("this script must be executed into the Airbite repo only")

sys.path.insert(0, str(ROOT_DIR / "airbyte-integrations/connectors"))
from tasks import CONFIG_FILE, TOOLS_VERSIONS, _run_task  # noqa

TASK_COMMANDS: Dict[str, List[str]] = {
    "black": [
        f"pip install black~={TOOLS_VERSIONS['black']}",
        f"XDG_CACHE_HOME={os.devnull} black -v {{check_option}} --diff {{source_path}}/. > {{reports_path}}/black.txt",
    ],
    "coverage": [
        "pip install .",
        f"pip install coverage[toml]~={TOOLS_VERSIONS['coverage']}",
        "coverage xml --fail-under 0 --rcfile={toml_config_file} -o {reports_path}/coverage.xml",
    ],
    "flake": [
        f"pip install mccabe~={TOOLS_VERSIONS['mccabe']}",
        f"pip install pyproject-flake8~={TOOLS_VERSIONS['flake']}",
        f"pip install flake8-junit-report~={TOOLS_VERSIONS['flake_junit']}",
        "pflake8 -v {source_path} --output-file={reports_path}/flake.txt --bug-report",
        "flake8_junit {reports_path}/flake.txt {reports_path}/flake.xml",
        "rm -f {reports_path}/flake.txt",
    ],
    "isort": [
        f"pip install colorama~={TOOLS_VERSIONS['colorama']}",
        f"pip install isort~={TOOLS_VERSIONS['isort']}",
        "isort -v {check_option} {source_path}/. > {reports_path}/isort.txt",
    ],
    "mypy": [
        "pip install .",
        f"pip install lxml~={TOOLS_VERSIONS['lxml']}",
        f"pip install mypy~={TOOLS_VERSIONS['mypy']}",
        "mypy {source_path} --config-file={toml_config_file} --cobertura-xml-report={reports_path}",
    ],
    "pycoverage": [
        f"pip install coverage[toml]~={TOOLS_VERSIONS['coverage']}",
        "mkdir {venv}/source-acceptance-test",
        "git ls-tree -r HEAD --name-only {source_acceptance_test_path} | while read src; do cp -f $src {venv}/source-acceptance-test; done",
        "pip install build",
        f"python -m build {os.path.join('{venv}', 'source-acceptance-test')}",
        f"pip install {os.path.join('{venv}', 'source-acceptance-test', 'dist', 'source_acceptance_test-*.whl')}",
        "[ -f requirements.txt ] && pip install --quiet -r requirements.txt",
        "pip install .",
        "pip install .[tests]",
        "coverage run -m pytest {source_path}/unit_tests || true",
        "coverage xml --fail-under 0 --skip-covered --omit=./*_tests/*,setup.py --rcfile={toml_config_file} -o {reports_path}/coverage.xml",
    ],
    "test": [
        "mkdir {venv}/source-acceptance-test",
        "git ls-tree -r HEAD --name-only {source_acceptance_test_path} | while read src; do cp -f $src {venv}/source-acceptance-test; done",
        "pip install build",
        f"python -m build {os.path.join('{venv}', 'source-acceptance-test')}",
        f"pip install {os.path.join('{venv}', 'source-acceptance-test', 'dist', 'source_acceptance_test-*.whl')}",
        "[ -f requirements.txt ] && pip install -r requirements.txt 2> /dev/null",
        "pip install .",
        "pip install .[tests]",
        "pip install pytest-cov",
        "pytest -v --cov={source_path} --cov-report xml:{reports_path}/pytest.xml {source_path}/unit_tests",
    ],
}


def print_commands(folder: str, output_folder: str, venv_folder: str, test_name: str) -> int:
    """Generates a suite of commands only"""
    if test_name not in TASK_COMMANDS:
        return LOGGER.error(f"not found the test suite '{test_name}', Available values: {TASK_COMMANDS.keys()}")

    toml_config_file = str(ROOT_DIR / "pyproject.toml")
    for cmd in TASK_COMMANDS[test_name]:
        rendered_cmd = cmd.replace(
            "{source_path}", folder.replace(str(CURRENT_DIR), ".")).replace(
            "{reports_path}", output_folder).replace(
            "{venv}", venv_folder).replace("{toml_config_file}", toml_config_file).replace(
            "{source_acceptance_test_path}", str(ROOT_DIR / "airbyte-integrations/bases/source-acceptance-test"))
        print(rendered_cmd, file=sys.stdout)
    return 0


def build_py_static_checkers_reports(folder: str, output_folder: str) -> int:
    ctx = Context()
    toml_config_file = str(ROOT_DIR / "pyproject.toml")

    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    LOGGER.info(f"created the report folder: {output_folder}")
    os.makedirs(output_folder)

    for checker in TASK_COMMANDS:
        LOGGER.info(f"start the test '{checker}'...")
        _run_task(
            ctx,
            f"{os.getcwd()}/{folder}",
            checker,
            module_path=folder,
            multi_envs=True,
            check_option="",
            task_commands=TASK_COMMANDS,
            toml_config_file=toml_config_file,
            reports_path=output_folder,
            source_acceptance_test_path=str(ROOT_DIR / "airbyte-integrations/bases/source-acceptance-test"),
        )
        LOGGER.info(f"stop the test '{checker} => {output_folder}'...")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Working with Python Static Report Builder.")
    parser.add_argument("changed_modules", nargs="*")
    parser.add_argument("--output_folder", help="Folder where all reports will be saved", required=False, type=str,
                        default=f"{os.getcwd()}/static_checker_reports")
    parser.add_argument("--print_commands", help="print of all test commands for a needed command only", required=False, type=str)
    parser.add_argument("--venv_folder", help="path to virtual env if needed", required=False, type=str, default=".")
    args = parser.parse_args()
    modules = [json.loads(m) for m in args.changed_modules]
    modules = {m['folder']: m for m in itertools.chain.from_iterable([m if isinstance(m, list) else [m] for m in modules])}

    for module in modules.values():
        output_folder = args.output_folder
        if len(modules) > 1:
            output_folder += "/" + module["module"].replace("/", "_")
        if not os.path.exists(module["folder"]):
            folder = ROOT_DIR / module["folder"]
            if folder.is_dir():
                LOGGER.info(f"corrected {module['folder']} => {folder}")
                module["folder"] = str(folder)
            else:
                return LOGGER.error(f"Not found the folders: {module['folder']} or {folder}")
        if args.print_commands:
            for suite in args.print_commands.split(","):
                if print_commands(
                        test_name=suite, venv_folder=args.venv_folder,
                        folder=module["folder"], output_folder=output_folder,
                ):
                    return 1
            return 0

        LOGGER.info(f"Found the module {module['module']}, lang: {module['lang']} => {output_folder}")
        if module["lang"] != "py":
            LOGGER.warning(f"Skipped the module: {module} because its tests are not supported now")
            continue
        elif "setup.py" not in os.listdir(module["folder"]):
            return LOGGER.error(f"Not found the setup.py file in the {module['folder']}")

        elif build_py_static_checkers_reports(folder=module["folder"], output_folder=output_folder):
            return 1
        LOGGER.info("all tests were finished...")
        return 0

    if __name__ == "__main__":
        sys.exit(main())
