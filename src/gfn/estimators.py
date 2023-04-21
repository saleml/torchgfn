from abc import ABC, abstractmethod

import torch.nn as nn
from torch.distributions import Distribution
from torchtyping import TensorType

from gfn.envs import Env, DiscreteEnv
from gfn.states import States

# Typing
OutputTensor = TensorType["batch_shape", "output_dim", float]


class FunctionEstimator(ABC):
    r"""Training a GFlowNet requires parameterizing one or more of the following functions:
    - $s \mapsto (\log F(s \rightarrow s'))_{s' \in Children(s)}$
    - $s \mapsto (P_F(s' \mid s))_{s' \in Children(s)}$
    - $s' \mapsto (P_B(s \mid s'))_{s \in Parents(s')}$
    - $s \mapsto (\log F(s))_{s \in States}$
    This class is the base class for all such function estimators. The estimators need to encapsulate
    a nn.Module, which takes a a batch of preprocessed states as input and outputs a batch of
    outputs of the desired shape. When the goal is to represent a probability distribution, the
    outputs would correspond to the parameters of the distribution, e.g. logits for a categorical
    distribution for discrete environments.
    The preprocessor is also encapsulated in the estimator via the
    environment. These function estimators implement the __call__ method, which takes
    States objects as inputs and calls the module on the preprocessed states.
    """

    def __init__(self, env: Env, module: nn.Module) -> None:
        """
        Args:
            env (Env): the environment.
            module (nn.Module): The module to use. If the module is a Tabular module (from `gfn.examples`), then the
                environment preprocessor needs to be an EnumPreprocessor.
        """
        self.env = env
        self.module = module
        self.preprocessor = env.preprocessor
        self.output_dim_is_checked = False

    def __call__(self, states: States) -> OutputTensor:
        out = self.module(self.preprocessor(states))
        if not self.output_dim_is_checked:
            self.check_output_dim(out)
            self.output_dim_is_checked = True

        return out

    @abstractmethod
    def check_output_dim(self, module_output: OutputTensor) -> None:
        """Check that the output of the module has the correct shape. Raises an error if not."""
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}({self.env})"

    def named_parameters(self) -> dict:
        return dict(self.module.named_parameters())

    def load_state_dict(self, state_dict: dict):
        self.module.load_state_dict(state_dict)


class LogEdgeFlowEstimator(FunctionEstimator):
    r"""Container for estimators $(s \rightarrow s') \mapsto \log F(s \rightarrow s')$.
    The way it's coded is a function $s \mapsto (\log F(s \rightarrow (s + a)))_{a \in \mathbb{A}}$,
    where $s+a$ is the state obtained by performing action $a$ in state $s$.

    This estimator is used for the flow-matching loss, which only supports discrete environments.
    # TODO: make it work for continuous environments.
    """

    def check_output_dim(self, module_output: OutputTensor):
        if not isinstance(self.env, DiscreteEnv):
            raise ValueError(
                "LogEdgeFlowEstimator only supports discrete environments."
            )
        if module_output.shape[-1] != self.env.n_actions:
            raise ValueError(
                f"LogEdgeFlowEstimator output dimension should be {self.env.n_actions}, but is {module_output.shape[-1]}."
            )


class LogStateFlowEstimator(FunctionEstimator):
    r"""Container for estimators $s \mapsto \log F(s)$."""

    def check_output_dim(self, module_output: OutputTensor):
        if module_output.shape[-1] != 1:
            raise ValueError(
                f"LogStateFlowEstimator output dimension should be 1, but is {module_output.shape[-1]}."
            )


class ProbabilityEstimator(FunctionEstimator, ABC):
    r"""Container for estimators of probability distributions.
    When calling (via __call__) such an estimator, an extra step is performed, which is to transform
    the output of the module into a probability distribution. This is done by applying the abstract
    `to_probability_distribution` method.

    The outputs of such an estimator are thus probability distributions, not the parameters of the
    distributions. For example, for a discrete environment, the output is a tensor of shape
    (batch_size, n_actions) containing the probabilities of each action.
    """

    @abstractmethod
    def to_probability_distribution(
        self, states: States, module_output: OutputTensor
    ) -> Distribution:
        """Transform the output of the module into a probability distribution."""
        pass

    def __call__(self, states: States) -> Distribution:
        return self.to_probability_distribution(states, super().__call__(states))


class LogZEstimator:
    # TODO: should this be a FunctionEstimator with a nn.Module as well?
    r"""Container for the estimator $\log Z$."""

    def __init__(self, tensor: TensorType[0, float]) -> None:
        self.tensor = tensor
        assert self.tensor.shape == ()
        self.tensor.requires_grad = True

    def __repr__(self) -> str:
        return str(self.tensor.item())

    def named_parameters(self) -> dict:
        return {"logZ": self.tensor}

    def load_state_dict(self, state_dict: dict):
        self.tensor = state_dict["logZ"]
