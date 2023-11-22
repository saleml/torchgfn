"""
Implementations of the [Trajectory Balance loss](https://arxiv.org/abs/2201.13259)
and the [Log Partition Variance loss](https://arxiv.org/abs/2302.05446).
"""

import torch
import torch.nn as nn
from torchtyping import TensorType as TT

from gfn.containers import Trajectories
from gfn.env import Env
from gfn.gflownet.base import TrajectoryBasedGFlowNet
from gfn.modules import GFNModule


class TBGFlowNet(TrajectoryBasedGFlowNet):
    r"""Holds the logZ estimate for the Trajectory Balance loss.

    $\mathcal{O}_{PFZ} = \mathcal{O}_1 \times \mathcal{O}_2 \times \mathcal{O}_3$, where
    $\mathcal{O}_1 = \mathbb{R}$ represents the possible values for logZ,
    and $\mathcal{O}_2$ is the set of forward probability functions consistent with the
    DAG. $\mathcal{O}_3$ is the set of backward probability functions consistent with
    the DAG, or a singleton thereof, if self.logit_PB is a fixed DiscretePBEstimator.

    Attributes:
        on_policy: Whether the GFlowNet samples trajectories on or off policy.
        logZ: a LogZEstimator instance.

    """

    def __init__(
        self,
        pf: GFNModule,
        pb: GFNModule,
        on_policy: bool = False,
        init_logZ: float = 0.0,
    ):
        super().__init__(pf, pb, on_policy=on_policy)

        self.logZ = nn.Parameter(torch.tensor(init_logZ))

    def loss(
        self,
        env: Env,
        trajectories: Trajectories,
        estimator_outputs: torch.Tensor = None,
    ) -> TT[0, float]:
        """Trajectory balance loss.

        The trajectory balance loss is described in 2.3 of
        [Trajectory balance: Improved credit assignment in GFlowNets](https://arxiv.org/abs/2201.13259))

        Raises:
            ValueError: if the loss is NaN.
        """
        del env  # unused
        _, _, scores = self.get_trajectories_scores(trajectories, estimator_outputs)
        loss = (scores + self.logZ).pow(2).mean()
        if torch.isnan(loss):
            raise ValueError("loss is nan")

        return loss


class LogPartitionVarianceGFlowNet(TrajectoryBasedGFlowNet):
    """Dataclass which holds the logZ estimate for the Log Partition Variance loss.

    Attributes:
        on_policy: Whether the GFlowNet samples trajectories on or off policy.

    Raises:
        ValueError: if the loss is NaN.
    """

    def __init__(
        self,
        pf: GFNModule,
        pb: GFNModule,
        on_policy: bool = False,
    ):
        super().__init__(pf, pb, on_policy=on_policy)

    def loss(
        self,
        env: Env,
        trajectories: Trajectories,
        estimator_outputs: torch.Tensor = None,
    ) -> TT[0, float]:
        """Log Partition Variance loss.

        This method is described in section 3.2 of
        [ROBUST SCHEDULING WITH GFLOWNETS](https://arxiv.org/abs/2302.05446))
        """
        del env  # unused
        _, _, scores = self.get_trajectories_scores(trajectories, estimator_outputs)
        loss = (scores - scores.mean()).pow(2).mean()
        if torch.isnan(loss):
            raise ValueError("loss is NaN.")

        return loss
