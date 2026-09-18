"""Domain-specific HTTP calls for the IRIS Atelier REST API."""

from prism.iris.api.compile import compile_documents
from prism.iris.api.documents import (
    DocumentNotFound,
    delete_document,
    get_document,
    list_documents,
    put_document,
)
from prism.iris.api.monitor import get_alerts, get_metrics
from prism.iris.api.server_info import get_server_info
from prism.iris.api.sql import execute_query
from prism.iris.api.terminal import TerminalError, execute_command
from prism.iris.api.testing import (
    ensure_runner_deployed,
    get_assertions,
    get_latest_results,
    get_test_history,
    list_test_classes,
    run_tests,
)

__all__ = [
    "DocumentNotFound",
    "TerminalError",
    "compile_documents",
    "delete_document",
    "ensure_runner_deployed",
    "execute_command",
    "execute_query",
    "get_alerts",
    "get_assertions",
    "get_document",
    "get_latest_results",
    "get_metrics",
    "get_server_info",
    "get_test_history",
    "list_documents",
    "list_test_classes",
    "put_document",
    "run_tests",
]
