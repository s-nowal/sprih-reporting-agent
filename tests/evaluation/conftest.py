"""Evaluation test configuration — load .env before any agent is imported."""

import os

from dotenv import load_dotenv

# Load .env so ANTHROPIC_API_KEY and SERPER_API_KEY are available
# before build_research_graph() instantiates the LLM client.
load_dotenv()
