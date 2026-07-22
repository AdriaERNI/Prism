"""Prism chatbot agent — an AI agent that orchestrates Prism's MCP tools.

The chatbot connects to an OpenAI-compatible LLM API and exposes all
registered Prism MCP tools as function-calling capabilities.  The LLM
decides which tools to call and in what order, based on the user's
natural-language request.

Optionally, a folder of "skills" (markdown files with instructions) can
be loaded and injected into the system prompt, giving the agent domain
knowledge about how to use the tools effectively.
"""
