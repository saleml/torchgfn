from typing import Dict

import torch
from torch.distributions import Categorical, Distribution


class UnsqueezedCategorical(Categorical):
    """Samples from a categorical distribution with an unsqueezed final dimension.

    Samples are unsqueezed to be of shape (batch_size, 1) instead of (batch_size,).

    This is used in `DiscretePFEstimator` and `DiscretePBEstimator`, which in turn are
    used in `Sampler`.

    This helper class facilitates representing actions, for discrete environments, which
    when implemented with the `DiscreteActions` class (see
    `gfn/env.py::DiscreteEnv), use an `action_shape = (1,)`. Therefore, according
    to `gfn/actions.py::Actions`, tensors representing actions in discrete environments
    should be of shape (batch_shape, 1).
    """

    def sample(self, sample_shape=torch.Size()) -> torch.Tensor:
        """Sample actions with an unsqueezed final dimension.

        Args:
            sample_shape: The shape of the sample.

        Returns the sampled actions as a tensor of shape (*sample_shape, *batch_shape, 1).
        """
        out = super().sample(sample_shape).unsqueeze(-1)
        assert out.shape == sample_shape + self._batch_shape + (1,)
        return out

    def log_prob(self, sample: torch.Tensor) -> torch.Tensor:
        """Returns the log probabilities of an unsqueezed sample.

        Args:
            sample: The sample of for which to compute the log probabilities.

        Returns the log probabilities of the sample as a tensor of shape (*sample_shape, *batch_shape).
        """
        assert sample.shape[-1] == 1
        return super().log_prob(sample.squeeze(-1))


class CompositeDistribution(
    Distribution
):  # TODO: may use CompositeDistribution in TensorDict
    """A mixture distribution."""

    def __init__(self, dists: Dict[str, Distribution]):
        """Initializes the mixture distribution.

        Args:
            dists: A dictionary of distributions.
        """
        super().__init__()
        self.dists = dists

    def sample(self, sample_shape=torch.Size()) -> Dict[str, torch.Tensor]:
        return {k: v.sample(sample_shape) for k, v in self.dists.items()}

    def log_prob(self, sample: Dict[str, torch.Tensor]) -> torch.Tensor:
        log_probs = [
            v.log_prob(sample[k]).reshape(sample[k].shape[0], -1).sum(dim=-1)
            for k, v in self.dists.items()
        ]
        # Note: this returns the sum of the log_probs over all the components
        # as it is a uniform mixture distribution.
        return sum(log_probs)


class CategoricalIndexes(Categorical):
    """Samples indexes from a categorical distribution."""

    def __init__(self, probs: torch.Tensor, node_indexes: torch.Tensor):
        """Initializes the distribution.

        Args:
            probs: The probabilities of the categorical distribution.
            n: The number of nodes in the graph.
        """
        self.node_indexes = node_indexes
        assert probs.shape == (
            probs.shape[0],
            node_indexes.shape[0] * node_indexes.shape[0],
        )
        super().__init__(probs)

    def sample(self, sample_shape=torch.Size()) -> torch.Tensor:
        samples = super().sample(sample_shape)
        out = torch.stack(
            [
                samples // self.node_indexes.shape[0],
                samples % self.node_indexes.shape[0],
            ],
            dim=-1,
        )
        out = self.node_indexes.index_select(0, out.flatten()).reshape(*out.shape)
        return out

    def log_prob(self, value):
        value = value[..., 0] * self.node_indexes.shape[0] + value[..., 1]
        value = torch.bucketize(value, self.node_indexes)
        return super().log_prob(value)


class CategoricalActionType(Categorical):  # TODO: remove, just to sample 1 action_type
    def __init__(self, probs: torch.Tensor):
        self.batch_len = len(probs)
        super().__init__(probs[0])

    def sample(self, sample_shape=torch.Size()) -> torch.Tensor:
        samples = super().sample(sample_shape)
        return samples.repeat(self.batch_len)

    def log_prob(self, value):
        return super().log_prob(value[0]).repeat(self.batch_len)
