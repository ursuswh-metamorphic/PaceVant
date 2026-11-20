from treasury_backend.modules.temporal.verifier import PRIORITY


def fuse(semantic, deterministic, *, shield_verdict="ALIGNED"):
    reasons = [v.code for v in deterministic.violations]
    reasons.extend(semantic.reason_codes)
    verdict = deterministic.verdict
    if semantic.verdict == "MISALIGNED" or shield_verdict == "MISALIGNED":
        verdict = "REJECT"
    elif semantic.verdict != "ALIGNED" and PRIORITY[verdict] < PRIORITY["ESCALATE"]:
        verdict = "ESCALATE"
    if shield_verdict != "ALIGNED" and PRIORITY[verdict] < PRIORITY["ESCALATE"]:
        verdict = "ESCALATE"
    return verdict, list(dict.fromkeys(reasons))
