"""Buckets a job title into intern / new_grad / engineering / product / gtm / other."""

import re

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


def categorize(title: str) -> str:
    if INTERN.search(title):
        return "intern"
    if NEW_GRAD.search(title):
        return "new_grad"
    if ENGINEERING.search(title):
        return "engineering"
    if PRODUCT.search(title):
        return "product"
    if GTM.search(title):
        return "gtm"
    return "other"
