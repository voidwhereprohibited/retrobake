"""RetroBake safety layer (owned by the security agent).

Every other module goes through these functions for user text, AI prompts/outputs,
builds and franchise/IP checks. See docs/security.md for the contract.
"""

from __future__ import annotations

from .disclaimer import DISCLAIMER, DISCLAIMER_SHORT
from .errors import InputRejected, OutputRejected, SandboxError
from .ipguard import check_title, find_ip, scrub_ip
from .outputs import validate_image, validate_name
from .promptguard import POLLINATIONS_REQUIRED_PARAMS, check_prompt, quote_user_text
from .sandbox import BuildLimits, BuildResult, BuildWorkspace, run_build
from .sanitizer import FIELDS, clean_choice, clean_text, safe_filename, safe_join, sanitize

__all__ = [
    "DISCLAIMER",
    "DISCLAIMER_SHORT",
    "FIELDS",
    "POLLINATIONS_REQUIRED_PARAMS",
    "BuildLimits",
    "BuildResult",
    "BuildWorkspace",
    "InputRejected",
    "OutputRejected",
    "SandboxError",
    "check_prompt",
    "check_title",
    "clean_choice",
    "clean_text",
    "find_ip",
    "quote_user_text",
    "run_build",
    "safe_filename",
    "safe_join",
    "sanitize",
    "scrub_ip",
    "validate_image",
    "validate_name",
]
