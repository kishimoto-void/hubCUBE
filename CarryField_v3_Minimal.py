#!/usr/bin/env python3
"""
CarryField v3 - Minimal Carry

設計方針:
- Carryは「過去を次へ運ぶ」ための最小責任のみを担う
- R(t+1) = decay * R(t) + Δ  のみ
- Adaptive / Geometry / Momentum / Boundary は外部から与えられる
- 自身は状態を持たず、純粋にpropagateするだけ
- hubCUBEのモジュラー構造に合致

将来拡張:
- BubbleForce, Repair, Waypoint, PhaseGraph などは別のFieldとして合成可能
"""

import torch
from typing import Optional, Callable


torch.manual_seed(42)


class CarryField:
    """
    最小Carryフィールド

    責任:
    - 指定されたdecayで過去residueを次ステップへ運ぶ
    - 外部から与えられる delta / effective_decay / boundaryを適用
    - 自身はvelocityやanomaly、linksを知らない
    """

    def __init__(self, default_decay: float = 0.87, default_cap: float = 3.0):
        self.default_decay = default_decay
        self.default_cap = default_cap

    def propagate(
        self,
        old_residue: torch.Tensor,
        delta: torch.Tensor,
        effective_decay: Optional[float] = None,
        boundary_fn: Optional[Callable[[torch.Tensor], torch.Tensor]] = None,
        extra_terms: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        最小のcarry処理

        R' = decay * R + Δ (+ extra_terms)

        - effective_decay: Fieldから与えられる状態依存的decay
        - boundary_fn: BoundaryField.limit() などから与えられる境界処理
        - extra_terms: MomentumFieldやGeometryFieldの貢献をベクトル和で合成
        """
        decay = effective_decay if effective_decay is not None else self.default_decay

        # 基本carry
        carried = old_residue * decay + delta

        # extra terms (Momentum, Geometryなどの合成)
        if extra_terms is not None:
            carried = carried + extra_terms

        # Boundary処理は外部に代行
        if boundary_fn is not None:
            new_residue = boundary_fn(carried)
        else:
            # 最小は簡易clamp (将来はBoundaryFieldに移行)
            new_residue = torch.clamp(carried, -self.default_cap, self.default_cap)

        return new_residue

    def compute_persistence(
        self,
        old_residue: torch.Tensor,
        new_residue: torch.Tensor,
        eps: float = 1e-8
    ) -> float:
        """
        真のpersistence計算

        例:
        - cosine similarity (dot / (|old| * |new|))
        - 情報がどれだけ残ったかを測定
        """
        old_norm = torch.norm(old_residue) + eps
        new_norm = torch.norm(new_residue) + eps
        cos_sim = torch.dot(old_residue.flatten(), new_residue.flatten()) / (old_norm * new_norm)
        return float(torch.clamp(cos_sim, -1.0, 1.0))


# 簡易使用例
if __name__ == "__main__":
    carry = CarryField(default_decay=0.87)

    old_r = torch.tensor([0.5, -0.3, 0.8, 0.1, -0.2])
    delta = torch.tensor([0.1, 0.05, -0.1, 0.0, 0.15])

    # 状態依存的decayを外部(Field)から与える例
    effective_d = 0.91
    new_r = carry.propagate(old_r, delta, effective_decay=effective_d)

    pers = carry.compute_persistence(old_r, new_r)
    print(f"Old: {old_r}")
    print(f"New: {new_r}")
    print(f"Persistence (cosine): {pers:.4f}")
