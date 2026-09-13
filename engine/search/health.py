"""Track D (`04-worker-build-plan.md` §5) — the run-health floor.

PoC-0b's correction 2 (`poc/poc0b-results.md`, "Real-run results — throttle
floor and cumulative-volume budget"; also `poc/poc0a-results.md` Addendum 2):
`04-worker-build-plan.md` §14 originally framed the open floor decision as a
maximum on *engines failed per query*. That axis is unusable — 119/120
queries (99%) in the full PoC-0b run carried at least one unresponsive
engine, so a floor on engines-failed rejects essentially the entire run;
there is no threshold on that axis that both excludes bad data and keeps
any.

The floor has to be defined on the opposite axis: **engines that returned**
— a minimum count of substantive engines answering a query — not engines
that failed. This module implements that axis only.

PoC-0 deliberately does not pick the number (`04-worker-build-plan.md` §2:
"do not bring a number for the `unresponsive_engines` floor... §14 already
lists the floor as open for exactly this reason"; PoC-0b's own conclusion:
"This run does not pick that number... but it does establish which axis the
number belongs on"). `MIN_ENGINES_RETURNED` below is therefore a named
placeholder, not a derived constant — see its docstring.
"""
from search.provider import CONFIGURED_ENGINES

# UNSET pending real-run data. `04-worker-build-plan.md` §14 lists this floor
# as an open decision on purpose, and PoC-0b's full 120-query run explicitly
# declined to pick a number for it (it only established which axis the floor
# belongs on — see this module's docstring). The value below is a
# placeholder so the function has a runnable default; it is NOT a
# recommendation and must not be treated as settled. Whoever sets the real
# number should derive it from a production run's engines-returned
# distribution, not from this constant.
MIN_ENGINES_RETURNED = 1


def engines_returned(response):
    """The count of configured engines that substantively answered a query
    — i.e. contributed at least one result. Derived from
    `SearchResponse.engines_seen_in_results`, not from the absence of
    `unresponsive_engines`, because `unresponsive_engines` is a lower bound
    on failure (PoC-0's central finding) and would overcount engines that
    silently returned nothing.
    """
    return len(response.engines_seen_in_results)


def is_healthy(response, min_engines_returned=MIN_ENGINES_RETURNED):
    """True if `response` meets the run-health floor.

    The floor is defined on engines-that-returned (a minimum count
    answering), never on engines-that-failed — see module docstring for why
    the latter axis is unusable at PoC-0's measured health level.

    `min_engines_returned` is a parameter, not a hardcoded threshold, so a
    caller can supply the real number once a production run has one; it
    defaults to `MIN_ENGINES_RETURNED`, which is itself explicitly unset
    pending that data.
    """
    return engines_returned(response) >= min_engines_returned


def run_health_summary(responses, min_engines_returned=MIN_ENGINES_RETURNED):
    """Aggregate health over a batch of `SearchResponse`s: count healthy vs
    degraded, and which configured engines were silently absent anywhere in
    the batch (a diagnostic, not itself part of the floor).
    """
    responses = list(responses)
    healthy = sum(1 for r in responses if is_healthy(r, min_engines_returned))
    degraded = len(responses) - healthy
    silently_absent_anywhere = sorted(
        {e for r in responses for e in r.silently_absent_engines}
    )
    return {
        "total": len(responses),
        "healthy": healthy,
        "degraded": degraded,
        "min_engines_returned": min_engines_returned,
        "silently_absent_anywhere": silently_absent_anywhere,
        "configured_engines": list(CONFIGURED_ENGINES),
    }
