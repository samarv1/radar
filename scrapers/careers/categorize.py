"""Classify job titles by function and seniority."""

import re
from dataclasses import dataclass
from typing import Literal

RoleType = Literal["engineering", "product", "gtm", "other"]
RoleLevel = Literal["intern", "new_grad", "experienced"]

INTERN = re.compile(
    r"\b(intern|internship|co-?op|apprentice|apprenticeship)\b",
    re.IGNORECASE,
)

NEW_GRAD = re.compile(
    r"\b(new.?grad|new graduate|recent grad|recent graduate|entry.?level|"
    r"university grad|campus hire|junior|associate engineer|associate software|"
    r"associate developer|associate data|associate product)\b",
    re.IGNORECASE,
)

ENGINEERING = re.compile(
    r"\b(engineer|engineering|developer|software|backend|front.?end|full.?stack|"
    r"data|ml|machine learning|ai|artificial intelligence|infrastructure|devops|"
    r"sre|site reliability|platform|security|qa|quality|hardware|embedded|firmware|"
    r"scientist|research scientist|applied|cloud|mobile|ios|android|systems)\b",
    re.IGNORECASE,
)

PRODUCT = re.compile(
    r"\b(product manager|product lead|pm\b|principal pm|"
    r"product designer|ux|ui\b|user experience|user research|"
    r"designer|design|researcher|research)\b",
    re.IGNORECASE,
)

GTM = re.compile(
    r"\b(sales|account executive|ae\b|sdr|bdr|business development|"
    r"marketing|growth|revenue|customer success|cs\b|customer support|"
    r"partnerships|partner|solutions engineer|solutions consultant|"
    r"demand generation|field|go.?to.?market|gtm|brand|content|"
    r"communications|pr\b|public relations|social media|community)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JobClassification:
    role_type: RoleType
    role_level: RoleLevel


def classify(title: str) -> JobClassification:
    if ENGINEERING.search(title):
        role_type: RoleType = "engineering"
    elif PRODUCT.search(title):
        role_type = "product"
    elif GTM.search(title):
        role_type = "gtm"
    else:
        role_type = "other"

    if INTERN.search(title):
        role_level: RoleLevel = "intern"
    elif NEW_GRAD.search(title):
        role_level = "new_grad"
    else:
        role_level = "experienced"

    return JobClassification(role_type=role_type, role_level=role_level)


def categorize(title: str) -> str:
    """Return the legacy exclusive category while callers migrate."""
    classification = classify(title)
    if classification.role_level != "experienced":
        return classification.role_level
    return classification.role_type
