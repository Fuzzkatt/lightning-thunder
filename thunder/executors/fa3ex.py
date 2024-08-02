import torch

"""
Currently we rely on the user / container to build fa3 following the install instructions
from https://github.com/Dao-AILab/flash-attention?tab=readme-ov-file#flashattention-3-beta-release.
fa3 is currently only built for sm90+ (hopper), so HAS_FA3 can only be True if and only if the device
is hopper and fa3 has been built
"""
try:
    from flash_attn_interface import _flash_attn_forward, _flash_attn_backward, flash_attn_func

    HAS_FA3 = True
except:
    HAS_FA3 = False

import thunder
from thunder.core.transforms import get_grad, put_grads
from thunder.extend import OperatorExecutor, register_executor

fa3_ex: OperatorExecutor = OperatorExecutor("fa3", version="0.1")
register_executor(fa3_ex)


def fa3_fwd_meta(
    q: thunder.torch.TensorLike,
    k: thunder.torch.TensorLike,
    v: thunder.torch.TensorLike,
    causal: bool = False,
    softmax_scale: float | None = None,
):
    return thunder.TensorProxy(like=q), thunder.TensorProxy(like=q, shape=(*q.shape[:1], 1))


def fa3_fwd_impl(
    q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, causal: bool = False, softmax_scale: float | None = None
):
    if not HAS_FA3:
        raise Exception("fa3 not built, cannot use fa3 executor")  # checker should fail before getting here

    # According to https://github.com/Dao-AILab/flash-attention/blob/5018ac6/README.md?plain=1, softmax_scale is
    # the scaling of QK^T before applying softmax. Default to 1 / sqrt(headdim).
    if softmax_scale is None:
        softmax_scale = q.shape[-1] ** (-0.5)
    q, k, v = (x.contiguous() for x in (q, k, v))
    out, q, k, v, out_padded, softmax_lse, S_dmask = _flash_attn_forward(q, k, v, softmax_scale, causal)
    return out, softmax_lse


def fa3_bwd_meta(
    dout: thunder.torch.TensorLike,
    q: thunder.torch.TensorLike,
    k: thunder.torch.TensorLike,
    v: thunder.torch.TensorLike,
    out: thunder.torch.TensorLike,
    softmax_lse,
    causal: bool = False,
    softmax_scale: None | float = None,
):

    grads = (thunder.TensorProxy(like=q), thunder.TensorProxy(like=k), thunder.TensorProxy(like=v))
    return grads


def fa3_bwd_impl(
    dout: torch.Tensor,
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    out: torch.Tensor,
    softmax_lse,
    causal: bool = False,
    softmax_scale: None | float = None,
):
    if not HAS_FA3:
        raise Exception("fa3 not built, cannot use fa3 executor")  # checker should fail before getting here

    dout, q, k, v, out = (x.contiguous() for x in (dout, q, k, v, out))

    dq, dk, dv = torch.empty_like(q), torch.empty_like(k), torch.empty_like(v)
    if softmax_scale is None:
        softmax_scale = q.shape[-1] ** (-0.5)
    _flash_attn_backward(
        dout,
        q,
        k,
        v,
        out,
        softmax_lse,
        dq,
        dk,
        dv,
        softmax_scale,
        causal,
    )
    dq = dq[
        ..., : dout.shape[-1]
    ]  # We could have padded the head dimension (from https://github.com/Dao-AILab/flash-attention/blob/5018ac6/hopper/flash_attn_interface.py#L179)
    dk = dk[..., : dout.shape[-1]]
    dv = dv[..., : dout.shape[-1]]
    grads = (dq, dk, dv)
    return grads


fa3_fwd = fa3_ex.register_operator("fa3_fwd", meta=fa3_fwd_meta, fn=fa3_fwd_impl)
fa3_bwd = fa3_ex.register_operator("fa3_bwd", meta=fa3_bwd_meta, fn=fa3_bwd_impl)


def fa3_checker(query, key, value, attn_mask=None, dropout_p=0.0, is_causal=False, scale=None):
    # fa3 needs to be built (implicitly also device check)
    if not HAS_FA3:
        return False

    # fa3 currently only supports headdim 64, 128, 256 for now
    if not (
        query.shape[3]
        in (
            64,
            128,
            256,
        )
        and key.shape[3]
        in (
            64,
            128,
            256,
        )
        and value.shape[3]
        in (
            64,
            128,
            256,
        )
    ):
        return False

    # fa3 currently only supports fp16 for now
    if (
        query.dtype != thunder.dtypes.float16
        or key.dtype != thunder.dtypes.float16
        or value.dtype != thunder.dtypes.float16
    ):
        return False

    # fa3 currently doesn't support attn_mask or dropout
    if attn_mask is not None or dropout_p != 0.0:
        return False

    return query.device.type == "cuda" and key.device == query.device and value.device == query.device


def fa3_execution_transform(
    q: thunder.TensorProxy,
    k: thunder.TensorProxy,
    v: thunder.TensorProxy,
    attn_mask: None | thunder.TensorProxy,
    dropout_p: float = 0.0,
    is_causal: bool = False,
    scale: None | float = None,
):
    out, softmax_lse = fa3_fwd(q, k, v, is_causal, softmax_scale=scale)
    return out


def fa3_grad_transform(
    q: thunder.TensorProxy,
    k: thunder.TensorProxy,
    v: thunder.TensorProxy,
    attn_mask: None | thunder.TensorProxy,
    dropout_p: float = 0.0,
    is_causal: bool = False,
    *,
    scale: None | float = None,
):
    out, softmax_lse = fa3_fwd(q, k, v, is_causal, softmax_scale=scale)
    grads = fa3_bwd(get_grad(out), q, k, v, out, softmax_lse, is_causal, softmax_scale=scale)
    dq, dk, dv = grads
    put_grads(
        (
            q,
            k,
            v,
        ),
        (
            dq,
            dk,
            dv,
        ),
    )
    return out


fa3_ex.register_implementation(
    thunder.torch.scaled_dot_product_attention,
    checker=fa3_checker,
    execution_transform=fa3_execution_transform,
    grad_transform=fa3_grad_transform,
)
