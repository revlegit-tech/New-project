# Phase 22 v2 Rate Limit + Local Env Hotfix

This hotfix makes Phase 22 safer for operator runs:

- Loads local `.env` through `local_env.load_local_env()` when available.
- Converts OddsPapi HTTP errors such as 429 into archived warning payloads.
- Keeps Phase 19 observed movement intact when OddsPapi is rate-limited or unavailable.

A 429 from OddsPapi means the provider request was accepted far enough to authenticate but was rate-limited. It is not a local data failure.
