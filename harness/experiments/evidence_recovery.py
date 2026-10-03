"""Named ablation variants; implementation lives in the normal layers."""

from harness.layers.critic import Critic
from harness.layers.retry import Retry
from harness.layers.evidence_recovery import QUERY_ALIASES


class FragmentCritic(Critic):
    def __init__(self):
        super().__init__(recover_fragments=True)


class QueryExpansionRetry(Retry):
    def __init__(self, max_attempts=3, reserve=1):
        super().__init__(max_attempts=max_attempts, reserve=reserve, query_mode='expanded')


class IntentRetrievalRetry(Retry):
    def __init__(self, max_attempts=3, reserve=1):
        super().__init__(max_attempts=max_attempts, reserve=reserve, query_mode='intent')
