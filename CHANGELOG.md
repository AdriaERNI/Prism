# Changelog

All notable changes to this project will be documented in this file.

## [0.1.2] - 2026-02-20

### Features

- Add execute_terminal tool for ObjectScript via WebSocket
- Stream terminal WebSocket output to agent via ctx.log()

### Documentation

- Document all environment variables

## [0.1.1] - 2026-02-19

### Bug Fixes

- Avoid file corruption on get document
- Standardize error handling across API and tools

### CI/CD

- Add CI and release pipelines

### Documentation

- Improve tool descriptions with examples and usage guidance

### Features

- Implement changelog system
- Add Workspace system
- Control JSON errors and return the error to the agent
- Add document name format validation
- Add configurable compile flags via env var
- Validate namespace access on startup
- Add ruff linter with format enforcement

### Refactoring

- Restructure the project
- Restructure tests
- Replace prints with logging in startup
- Use shared httpx client with connection pooling
- Make config env-based and API versions configurable

### Testing

- Unittests for api endpoints


