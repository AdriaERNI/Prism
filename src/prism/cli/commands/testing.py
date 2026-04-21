"""`prism test` and `prism list-tests` — unit test execution and discovery."""

from __future__ import annotations

import asyncio
import sys

import typer

from prism.output import get_output_format
from prism.iris.api.testing import list_test_classes, run_tests
from prism.output import format_output


def test(
    test_class: str = typer.Argument(
        ..., help="Test class to execute (e.g. MyApp.Tests.Calc)"
    ),
    method: str = typer.Option(
        "", "--method", "-m", help="Run a single test method instead of the whole class"
    ),
    manager: str = typer.Option(
        None,
        "--manager",
        help="Override the test manager class (defaults to IRIS_TEST_MANAGER_CLASS)",
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """Run a unit test class via the deployed runner."""
    try:
        response = asyncio.run(
            run_tests(
                test_class,
                test_method=method,
                manager_class=manager,
                namespace=namespace,
            )
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(format_output(response, get_output_format()))


def list_tests(
    filter: str = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter by class name prefix (e.g. MyApp.Tests)",
    ),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Target namespace (defaults to IRIS_NAMESPACE)"
    ),
) -> None:
    """List %UnitTest.TestCase classes and their Test* methods."""
    try:
        response = asyncio.run(
            list_test_classes(filter_prefix=filter, namespace=namespace)
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    typer.echo(format_output(response, get_output_format()))
