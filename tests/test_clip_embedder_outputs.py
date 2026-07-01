import pytest
import torch

from src.clip_embedder import _feature_tensor


class OutputWithPool:
    def __init__(self, tensor):
        self.pooler_output = tensor


class OutputWithHiddenState:
    def __init__(self, tensor):
        self.last_hidden_state = tensor


def test_feature_tensor_accepts_direct_tensor():
    tensor = torch.ones((2, 3))

    assert _feature_tensor(tensor) is tensor


def test_feature_tensor_accepts_pooler_output():
    tensor = torch.ones((2, 3))

    assert _feature_tensor(OutputWithPool(tensor)) is tensor


def test_feature_tensor_pools_last_hidden_state():
    tensor = torch.tensor([[[1.0, 3.0], [3.0, 5.0]]])

    pooled = _feature_tensor(OutputWithHiddenState(tensor))

    assert torch.equal(pooled, torch.tensor([[2.0, 4.0]]))


def test_feature_tensor_rejects_unknown_output():
    with pytest.raises(TypeError):
        _feature_tensor(object())
