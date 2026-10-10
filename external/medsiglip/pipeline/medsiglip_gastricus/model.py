"""方案 4 / 5 / 6.1: 帧内融合、变长聚合、MLP 头。输入是已缓存的 1152-d e_full / e_roi。

4.1 concat    ConcatFusion     u = MLP([e_full, e_roi])
4.2 interact  FrameFusion      u = MLP([full, roi, |full-roi|, full*roi])
4.gate        GateFusion       每帧门控混合两视图再投影
4.pair        PairAttnFusion   每帧 [full, roi] 两 token 自注意力
5.1           MeanViewPool     z = [mean(e_full), mean(e_roi)]，跳过 4.x
5.2           StatsPool        concat(mean, max, std) of u
5.3           GatedAttentionPool  a = softmax(w^T tanh(V u)); 再拼 attn/mean/max
5.mean_u      MeanUPool        先 4.x 再对 u 取均值
5.attn_only   GatedAttentionPool 只要 attention，不拼 mean/max
6.1           PatientHead      [z_image, clinical] -> MLP -> 4 类

--size small 对齐方案字面宽度（4.1 2304->512->256，4.2 4608->1024->256，5.3 维 128）。
默认 xlarge 更宽。wideclf 只加宽 6.1 分类头。deep 加帧 Transformer，持有集未升格。
方案 5.3 写 64-128 维；xlarge / wideclf 用 512。
"""

from __future__ import annotations

from typing import Sequence

import torch
from torch import nn

# small = 方案 4.1 / 4.2 / 5.3 字面宽度。其余档是仓库加宽，不是方案原文。
SIZE_PRESETS = {
    "small": {
        "fusion_dims_concat": (2304, 512, 256),
        "fusion_dims_interact": (4608, 1024, 256),
        "fusion_out": 256,
        "pool_out": 128,
        "attn_hidden": 128,
        "head_hidden": (64,),
        "dropout": 0.2,
    },
    "large": {
        "fusion_dims_concat": (2304, 1024, 512, 512),
        "fusion_dims_interact": (4608, 2048, 1024, 512),
        "fusion_out": 512,
        "pool_out": 256,
        "attn_hidden": 256,
        "head_hidden": (256, 128),
        "dropout": 0.3,
    },
    "xlarge": {
        "fusion_dims_concat": (2304, 2048, 1024, 512),
        "fusion_dims_interact": (4608, 4096, 2048, 512),
        "fusion_out": 512,
        "pool_out": 512,
        "attn_hidden": 512,
        "head_hidden": (1024, 512),
        "dropout": 0.35,
    },
    "xxlarge": {
        "fusion_dims_concat": (2304, 4096, 2048, 1024, 768),
        "fusion_dims_interact": (4608, 4096, 2048, 1024, 768),
        "fusion_out": 768,
        "pool_out": 768,
        "attn_hidden": 768,
        "head_hidden": (2048, 1024, 512),
        "dropout": 0.35,
    },
    "deep": {
        "fusion_dims_concat": (2304, 2048, 1536, 1024),
        "fusion_dims_interact": (4608, 4096, 2048, 1024),
        "fusion_out": 1024,
        "pool_out": 1024,
        "attn_hidden": 1024,
        "attn_heads": 8,
        "pool_layers": 4,
        "fusion_blocks": 3,
        "head_hidden": (2048, 1024, 512),
        "head_blocks": 2,
        "dropout": 0.25,
    },
    "wideclf": {
        "fusion_dims_concat": (2304, 2048, 1024, 512),
        "fusion_dims_interact": (4608, 4096, 2048, 512),
        "fusion_out": 512,
        "pool_out": 512,
        "attn_hidden": 512,
        "head_hidden": (4096, 2048, 1024, 512),
        "head_blocks": 2,
        "dropout": 0.3,
    },
    "mid": {
        "fusion_dims_concat": (2304, 2048, 1024, 512),
        "fusion_dims_interact": (4608, 4096, 2048, 512),
        "fusion_out": 512,
        "pool_out": 512,
        "attn_hidden": 512,
        "attn_heads": 4,
        "pool_layers": 2,
        "head_hidden": (1024, 512),
        "dropout": 0.3,
    },
}


def build_mlp(dims: Sequence[int], dropout: float, last_activation: bool = True) -> nn.Sequential:
    layers: list[nn.Module] = []
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        is_last = i == len(dims) - 2
        if not is_last or last_activation:
            layers.append(nn.LayerNorm(dims[i + 1]))
            layers.append(nn.GELU())
            layers.append(nn.Dropout(dropout))
    return nn.Sequential(*layers)


class ResidualMLP(nn.Module):
    def __init__(self, dims: Sequence[int], dropout: float) -> None:
        super().__init__()
        self.net = build_mlp(dims, dropout, last_activation=True)
        self.skip = nn.Identity() if dims[0] == dims[-1] else nn.Linear(dims[0], dims[-1])
        self.norm = nn.LayerNorm(dims[-1])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(self.net(x) + self.skip(x))


class ConcatFusion(nn.Module):
    """方案 4.1 简单基线: u[i,j] = MLP([e_full, e_roi])。small 为 2304 -> 512 -> 256。"""

    def __init__(self, dims: Sequence[int], dropout: float, residual: bool = True, n_blocks: int = 1) -> None:
        super().__init__()
        self.net = ResidualMLP(dims, dropout) if residual else build_mlp(dims, dropout, last_activation=True)
        hidden = int(dims[-1])
        extra = max(int(n_blocks) - 1, 0)
        self.blocks = nn.ModuleList(
            [ResidualMLP((hidden, hidden * 2, hidden), dropout) for _ in range(extra)]
        )

    def forward(self, e_full: torch.Tensor, e_roi: torch.Tensor) -> torch.Tensor:
        x = self.net(torch.cat([e_full, e_roi], dim=-1))
        for block in self.blocks:
            x = block(x)
        return x


class FrameFusion(nn.Module):
    """方案 4.2 增强版: u = MLP([e_full, e_roi, |e_full-e_roi|, e_full*e_roi])。small 为 4608 -> 1024 -> 256。"""

    def __init__(self, dims: Sequence[int], dropout: float, residual: bool = True, n_blocks: int = 1) -> None:
        super().__init__()
        self.net = ResidualMLP(dims, dropout) if residual else build_mlp(dims, dropout, last_activation=True)
        hidden = int(dims[-1])
        extra = max(int(n_blocks) - 1, 0)
        self.blocks = nn.ModuleList(
            [ResidualMLP((hidden, hidden * 2, hidden), dropout) for _ in range(extra)]
        )

    def forward(self, e_full: torch.Tensor, e_roi: torch.Tensor) -> torch.Tensor:
        feats = torch.cat([e_full, e_roi, (e_full - e_roi).abs(), e_full * e_roi], dim=-1)
        x = self.net(feats)
        for block in self.blocks:
            x = block(x)
        return x


class GateFusion(nn.Module):
    """每帧学一个通道门：u = proj(g * full + (1-g) * roi)。不是方案 4.1/4.2。"""

    def __init__(self, embed_dim: int, out_dim: int, dropout: float) -> None:
        super().__init__()
        self.gate = nn.Sequential(
            nn.Linear(embed_dim * 3, embed_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(embed_dim, embed_dim),
            nn.Sigmoid(),
        )
        self.proj = ResidualMLP((embed_dim, max(out_dim, embed_dim), out_dim), dropout)

    def forward(self, e_full: torch.Tensor, e_roi: torch.Tensor) -> torch.Tensor:
        g = self.gate(torch.cat([e_full, e_roi, (e_full - e_roi).abs()], dim=-1))
        return self.proj(g * e_full + (1.0 - g) * e_roi)


class PairAttnFusion(nn.Module):
    """每帧把 full / ROI 当成两个 token 做自注意力，再投影。"""

    def __init__(self, embed_dim: int, out_dim: int, dropout: float, n_heads: int = 4) -> None:
        super().__init__()
        heads = int(n_heads) if embed_dim % int(n_heads) == 0 else 1
        self.attn = nn.MultiheadAttention(embed_dim, heads, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(embed_dim)
        self.proj = ResidualMLP((embed_dim * 2, max(out_dim * 2, out_dim), out_dim), dropout)

    def forward(self, e_full: torch.Tensor, e_roi: torch.Tensor) -> torch.Tensor:
        bsz, frames, dim = e_full.shape
        pair = torch.stack([e_full, e_roi], dim=2).reshape(bsz * frames, 2, dim)
        attn_out, _ = self.attn(pair, pair, pair, need_weights=False)
        pair = self.norm(pair + attn_out).reshape(bsz, frames, dim * 2)
        return self.proj(pair)


def _masked_mean(frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    filled = frames.masked_fill(~valid.unsqueeze(-1), 0.0)
    denom = valid.sum(dim=1).clamp(min=1).unsqueeze(-1)
    return filled.sum(dim=1) / denom


def _masked_max(frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    neg_inf = torch.finfo(frames.dtype).min
    values = frames.masked_fill(~valid.unsqueeze(-1), neg_inf).max(dim=1).values
    return torch.where(valid.any(dim=1).unsqueeze(-1), values, torch.zeros_like(values))


def _masked_std(frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    mean = _masked_mean(frames, valid)
    n = valid.sum(dim=1).clamp(min=2).unsqueeze(-1)
    filled = frames.masked_fill(~valid.unsqueeze(-1), 0.0)
    var = ((filled - mean.unsqueeze(1)) ** 2 * valid.unsqueeze(-1)).sum(dim=1) / (n - 1)
    return torch.sqrt(var.clamp(min=0.0))


class MeanViewPool(nn.Module):
    """方案 5.1 BASELINE: z_image = [mean(e_full), mean(e_roi)]。默认 2304 维直出，不经过 4.x 融合。"""

    def __init__(self, embed_dim: int, out_dim: int | None, dropout: float) -> None:
        super().__init__()
        self.out_dim = embed_dim * 2 if out_dim is None else out_dim
        self.proj = (
            None
            if out_dim is None
            else build_mlp((embed_dim * 2, max(out_dim * 2, out_dim), out_dim), dropout, last_activation=True)
        )

    def forward(self, e_full: torch.Tensor, e_roi: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        z = torch.cat([_masked_mean(e_full, valid), _masked_mean(e_roi, valid)], dim=-1)
        return z if self.proj is None else self.proj(z)


class StatsPool(nn.Module):
    """方案 5.2 统计池化: z = concat(mean(u), max(u), std(u))，再投影。对融合后的 u 做，不是对 raw 视图。"""

    def __init__(self, dim: int, out_dim: int, dropout: float) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(dim * 3)
        self.proj = build_mlp((dim * 3, max(out_dim * 2, out_dim), out_dim), dropout, last_activation=True)

    def forward(self, frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        stats = torch.cat([_masked_mean(frames, valid), _masked_max(frames, valid), _masked_std(frames, valid)], dim=-1)
        return self.proj(self.norm(stats))


class MeanUPool(nn.Module):
    """先 4.x 得到 u，再对变长袋取均值。和 5.1 不同：5.1 对 raw 两视图分别平均。"""

    def __init__(self, dim: int, out_dim: int, dropout: float) -> None:
        super().__init__()
        self.out_dim = int(out_dim)
        self.proj = (
            nn.Identity()
            if int(dim) == int(out_dim)
            else build_mlp((dim, max(out_dim * 2, out_dim), out_dim), dropout, last_activation=True)
        )

    def forward(self, frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        return self.proj(_masked_mean(frames, valid))


class GatedAttentionPool(nn.Module):
    """方案 5.3: a = softmax(w^T tanh(V u)); z_attn = sum a*u；再拼 attn/mean/max 后投影。

    score = Linear -> Tanh -> Linear(H)，H=1 时就是方案里的 V 和 w。无效帧填 -1e4 再 softmax。
    deep 先过帧 Transformer，再用多头 gated。方案写投影到 64-128 维；small 默认 128，xlarge 512，deep 1024。
    """

    def __init__(
        self,
        dim: int,
        attn_hidden: int,
        out_dim: int,
        dropout: float,
        n_heads: int = 1,
        n_layers: int = 0,
        use_stats: bool = True,
    ) -> None:
        super().__init__()
        self.use_stats = bool(use_stats)
        self.encoder = None
        if int(n_layers) > 0:
            enc_heads = int(n_heads) if dim % int(n_heads) == 0 else 1
            layer = nn.TransformerEncoderLayer(
                d_model=dim,
                nhead=enc_heads,
                dim_feedforward=dim * 4,
                dropout=dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=int(n_layers))
        self.n_score = max(int(n_heads), 1)
        self.score = nn.Sequential(
            nn.Linear(dim, attn_hidden),
            nn.Tanh(),
            nn.Linear(attn_hidden, self.n_score),
        )
        proj_in = dim * (self.n_score + (2 if self.use_stats else 0))
        self.proj = build_mlp((proj_in, max(out_dim * 2, out_dim), out_dim), dropout, last_activation=True)

    def forward(self, frames: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        if self.encoder is not None:
            frames = self.encoder(frames, src_key_padding_mask=~valid)
        logits = self.score(frames)
        logits = logits.masked_fill(~valid.unsqueeze(-1), -1e4)
        attn = torch.softmax(logits, dim=1)
        pooled = torch.einsum("bth,btc->bhc", attn, frames).reshape(frames.size(0), -1)
        if not self.use_stats:
            return self.proj(pooled)
        return self.proj(torch.cat([pooled, _masked_mean(frames, valid), _masked_max(frames, valid)], dim=-1))


class PatientHead(nn.Module):
    """方案 6.1: [z_image, processed clinical] -> MLP -> 4 类。clinical_dim=0 则只走影像。"""

    def __init__(
        self,
        image_dim: int,
        clinical_dim: int,
        hidden: Sequence[int],
        dropout: float,
        n_classes: int = 4,
        residual: bool = False,
        n_blocks: int = 1,
    ) -> None:
        super().__init__()
        self.clinical_dim = clinical_dim
        in_dim = image_dim + clinical_dim
        self.residual = bool(residual) and bool(hidden)
        if self.residual:
            self.stem = ResidualMLP((in_dim, *hidden), dropout)
            last = int(hidden[-1])
            extra = max(int(n_blocks) - 1, 0)
            self.blocks = nn.ModuleList(
                [ResidualMLP((last, last * 2, last), dropout) for _ in range(extra)]
            )
            self.out = nn.Linear(last, n_classes)
            self.mlp = None
        else:
            self.mlp = build_mlp((in_dim, *hidden, n_classes), dropout, last_activation=False)

    def forward(self, image: torch.Tensor, clinical: torch.Tensor) -> torch.Tensor:
        x = image if self.clinical_dim == 0 else torch.cat([image, clinical], dim=-1)
        if self.mlp is not None:
            return self.mlp(x)
        x = self.stem(x)
        for block in self.blocks:
            x = block(x)
        return self.out(x)


class GastricUSFromScratch(nn.Module):
    """方案 4 + 5 + 6.1 拼装。mean_views 时 _image 不调用 fusion（5.1 跳过 4.x）。"""

    def __init__(
        self,
        clinical_dim: int = 22,
        fusion: str = "concat",
        pool: str = "gated",
        size: str = "xlarge",
        pool_proj: bool = True,
        residual: bool = True,
        aux_serosa: bool = False,
        pool_out: int | None = None,
        n_classes: int = 4,
        embed_dim: int = 1152,
    ) -> None:
        super().__init__()
        if fusion not in {"concat", "interact", "gate", "pair"}:
            raise ValueError(fusion)
        if pool not in {"mean_views", "stats", "gated", "mean_u", "attn_only"}:
            raise ValueError(pool)
        if size not in SIZE_PRESETS:
            raise ValueError(size)
        cfg = SIZE_PRESETS[size]
        self.fusion_name = fusion
        self.pool_name = pool
        self.size_name = size
        self.clinical_dim = clinical_dim
        self.embed_dim = int(embed_dim)
        dropout = float(cfg["dropout"])
        fusion_out = int(cfg["fusion_out"])
        pool_out = int(pool_out) if pool_out is not None else int(cfg["pool_out"])
        concat_dims = (self.embed_dim * 2,) + tuple(cfg["fusion_dims_concat"][1:])
        interact_dims = (self.embed_dim * 4,) + tuple(cfg["fusion_dims_interact"][1:])
        fusion_blocks = int(cfg.get("fusion_blocks", 1))
        if fusion == "concat":
            self.fusion = ConcatFusion(concat_dims, dropout, residual=residual, n_blocks=fusion_blocks)
        elif fusion == "interact":
            self.fusion = FrameFusion(interact_dims, dropout, residual=residual, n_blocks=fusion_blocks)
        elif fusion == "gate":
            self.fusion = GateFusion(self.embed_dim, fusion_out, dropout)
        else:
            self.fusion = PairAttnFusion(
                self.embed_dim, fusion_out, dropout, n_heads=int(cfg.get("attn_heads", 4))
            )
        if pool == "mean_views":
            out_dim = pool_out if pool_proj else None
            self.pool = MeanViewPool(self.embed_dim, out_dim, dropout)
            image_dim = self.pool.out_dim
        elif pool == "stats":
            self.pool = StatsPool(fusion_out, pool_out, dropout)
            image_dim = pool_out
        elif pool == "mean_u":
            self.pool = MeanUPool(fusion_out, pool_out, dropout)
            image_dim = pool_out
        else:
            self.pool = GatedAttentionPool(
                fusion_out,
                int(cfg["attn_hidden"]),
                pool_out,
                dropout,
                n_heads=int(cfg.get("attn_heads", 1)),
                n_layers=int(cfg.get("pool_layers", 0)),
                use_stats=pool == "gated",
            )
            image_dim = pool_out
        self.n_classes = n_classes
        self.head = PatientHead(
            image_dim,
            clinical_dim,
            cfg["head_hidden"],
            dropout,
            n_classes=n_classes,
            residual=residual and size in {"deep", "wideclf"},
            n_blocks=int(cfg.get("head_blocks", 1)),
        )
        self.serosa = nn.Linear(image_dim + clinical_dim, 1) if aux_serosa else None

    def n_parameters(self) -> int:
        return int(sum(p.numel() for p in self.parameters() if p.requires_grad))

    def _image(self, e_full: torch.Tensor, e_roi: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
        # 5.1 对 raw 视图取均值；5.2 / 5.3 先 4.x 融合再池化。
        if self.pool_name == "mean_views":
            return self.pool(e_full, e_roi, valid)
        return self.pool(self.fusion(e_full, e_roi), valid)

    def _patient_feat(self, image: torch.Tensor, clinical: torch.Tensor) -> torch.Tensor:
        if self.clinical_dim == 0:
            return image
        return torch.cat([image, clinical], dim=-1)

    def forward(
        self,
        e_full: torch.Tensor,
        e_roi: torch.Tensor,
        valid: torch.Tensor,
        clinical: torch.Tensor,
        return_aux: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        image = self._image(e_full, e_roi, valid)
        logits = self.head(image, clinical)
        if return_aux and self.serosa is not None:
            return logits, self.serosa(self._patient_feat(image, clinical)).squeeze(-1)
        return logits
