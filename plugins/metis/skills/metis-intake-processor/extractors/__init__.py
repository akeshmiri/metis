"""Intake extractors for UIF generation.

**All six sources, ported from Atlas.** Only Jira came across at first, and the
registry said so honestly -- the other five "were removed rather than carried
along disabled, so nothing here advertises a source it cannot actually process."
That was the right call while they were absent and the wrong state to stay in:
Confluence, Swagger, Zephyr Scale, code and database are precisely the sources
Requirements have to be built from, and reaching into another project's tree for
them is the coupling this port exists to remove.

Every one was cleanly portable -- four have no non-stdlib dependency at all and
`swagger_extractor` needs only `yaml`.

**Each was audited for the defect the Jira port found**, not just copied: the
Atlas original truncated `description` to 200 characters, which silently
destroyed requirement text mid-word. `confluence_extractor` carried the same cap
on the same field and it is removed here for the same reason -- in this pipeline
the description IS the evidence that gets mined into Requirements.
"""

from .base_extractor import BaseExtractor
from .code_extractor import CodeExtractor
from .confluence_extractor import ConfluenceExtractor
from .database_extractor import DatabaseExtractor
from .jira_extractor import JiraExtractor
from .scale_extractor import ScaleExtractor
from .swagger_extractor import SwaggerExtractor

__all__ = [
    "BaseExtractor",
    "CodeExtractor",
    "ConfluenceExtractor",
    "DatabaseExtractor",
    "JiraExtractor",
    "ScaleExtractor",
    "SwaggerExtractor",
]
