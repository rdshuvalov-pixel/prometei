#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class PlatformLane(str, Enum):
    ats_api = "ats_api"
    html_jsonld = "html_jsonld"
    playwright = "playwright"
    aggregator_api = "aggregator_api"
    not_searchable = "not_searchable"


class PlatformKind(str, Enum):
    greenhouse_board = "greenhouse_board"
    lever_board = "lever_board"
    workable_board = "workable_board"
    ashby_board = "ashby_board"
    teamtailor_board = "teamtailor_board"
    smartrecruiters_board = "smartrecruiters_board"
    jobvite_board = "jobvite_board"
    jazzhr_board = "jazzhr_board"
    workday_board = "workday_board"
    linkedin_company = "linkedin_company"
    notion_page = "notion_page"
    generic_site = "generic_site"


@dataclass(frozen=True)
class DetectedPlatform:
    kind: PlatformKind
    lane: PlatformLane
    canonical: str


_HOST_EQUIV = {
    "job-boards.greenhouse.io": "greenhouse",
    "boards-api.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "apply.workable.com": "workable",
    "jobs.ashbyhq.com": "ashby",
    "api.ashbyhq.com": "ashby",
}


def _host(url: str) -> str:
    h = (urlparse(url).netloc or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def detect_platform(url: str) -> DetectedPlatform:
    u = url.strip()
    h = _host(u)
    path = (urlparse(u).path or "").lower()

    # Explicitly not searchable without adapter
    if h in ("notion.site",) or h.endswith(".notion.site"):
        return DetectedPlatform(PlatformKind.notion_page, PlatformLane.playwright, "notion")
    if h == "linkedin.com" or h.endswith(".linkedin.com"):
        return DetectedPlatform(PlatformKind.linkedin_company, PlatformLane.playwright, "linkedin")

    # ATS patterns (prefer API lane where available, else Playwright)
    if h.endswith("greenhouse.io"):
        # pages like https://job-boards.greenhouse.io/{token}
        if re.search(r"^/[^/]+/?$", path) and "job-boards.greenhouse.io" in h:
            return DetectedPlatform(PlatformKind.greenhouse_board, PlatformLane.ats_api, "greenhouse")
        return DetectedPlatform(PlatformKind.greenhouse_board, PlatformLane.playwright, "greenhouse")
    if h == "jobs.lever.co":
        return DetectedPlatform(PlatformKind.lever_board, PlatformLane.ats_api, "lever")
    if h == "apply.workable.com":
        return DetectedPlatform(PlatformKind.workable_board, PlatformLane.ats_api, "workable")
    if h == "jobs.ashbyhq.com" or h == "api.ashbyhq.com":
        return DetectedPlatform(PlatformKind.ashby_board, PlatformLane.ats_api, "ashby")
    if h.endswith("teamtailor.com") or h.endswith("teamtailor.com."):
        return DetectedPlatform(PlatformKind.teamtailor_board, PlatformLane.playwright, "teamtailor")
    if h == "jobs.smartrecruiters.com":
        return DetectedPlatform(PlatformKind.smartrecruiters_board, PlatformLane.playwright, "smartrecruiters")
    if "jobvite.com" in h:
        return DetectedPlatform(PlatformKind.jobvite_board, PlatformLane.playwright, "jobvite")
    if h.endswith("jazzhr.com") or h == "jazzhr.com":
        return DetectedPlatform(PlatformKind.jazzhr_board, PlatformLane.playwright, "jazzhr")
    if "workdayjobs.com" in h:
        return DetectedPlatform(PlatformKind.workday_board, PlatformLane.playwright, "workday")

    canonical = _HOST_EQUIV.get(h, h or "unknown")
    return DetectedPlatform(PlatformKind.generic_site, PlatformLane.html_jsonld, canonical)

