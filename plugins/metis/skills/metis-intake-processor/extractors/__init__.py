"""Jira extractor for UIF generation.

Scoped deliberately to Jira. The Atlas original shipped six extractors
(Confluence, Swagger, Zephyr Scale, code, database); those were removed rather
than carried along disabled, so nothing here advertises a source it cannot
actually process.
"""

from .base_extractor import BaseExtractor
from .jira_extractor import JiraExtractor

__all__ = ["BaseExtractor", "JiraExtractor"]
