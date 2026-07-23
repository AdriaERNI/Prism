"""Domain-specific HTTP calls for the IRIS Atelier REST API."""

from prism.iris.api.server_info import get_server_info
from prism.iris.api.sql import execute_query
from prism.iris.api.documents import (
    list_documents,
    get_document,
    put_document,
    delete_document,
    DocumentNotFound,
)
from prism.iris.api.compile import compile_documents
from prism.iris.api.terminal import execute_command, TerminalError
from prism.iris.api.monitor import get_metrics, get_alerts
from prism.iris.api.testing import (
    ensure_runner_deployed,
    run_tests,
    get_latest_results,
    get_assertions,
    get_test_history,
    list_test_classes,
)

__all__ = [
    "get_server_info",
    "execute_query",
    "execute_command",
    "list_documents",
    "get_document",
    "put_document",
    "delete_document",
    "compile_documents",
    "DocumentNotFound",
    "TerminalError",
    "ensure_runner_deployed",
    "run_tests",
    "get_latest_results",
    "get_assertions",
    "get_test_history",
    "list_test_classes",
    "get_metrics",
    "get_alerts",
]
