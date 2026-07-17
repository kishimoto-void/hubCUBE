#!/usr/bin/env python3
"""
CarryForce v4 - Pure Force Generator (no state update)

設計方針 (v4 改善版):
- Carryは「力を生成する」たけのモジュールに結屈
- 状態更新は一切しない
- 返すのは carry_force のみ
  carry_force = old_residue * persistence   (または簡易に old * decay)
- Dynamics Solver が他のForceと合成して新状態を計算する

これでCarryは完全に「Force Generator」になり、
Geometry / Boundary はConstraintとして分離される
"""

import torch
from typing import Optional


torch.manual_seed(42)


class CarryForce:
    """
    純粋なCarry Force Generator

    返すのは「力」のみ。
    状態更新や保存は一切行わない。
    """

    def __init__(self, default_persistence: float = 0.87):
        self.default_persistence = default_persistence

    def compute_force(
        self,
        old_residue: torch.Tensor,
        persistence: Optional[float] = None,
        extra_multiplier: float = 1.0,
    ) -> torch.Tensor:
        """
        Carry力を計算して返すだけ

        carry_force = old_residue * persistence * extra_multiplier

        注: このモジュールは、
        - 新状態を計算しない
        - velocityやtensionを生成しない
        - anomalyやlinksに関与しない
        """
        p = persistence if persistence is not None else self.default_persistence
        carry_force = old_residue * p * extra_multiplier
        return carry_force

    def compute_persistence(
        self,
        old_residue: torch.Tensor,
        new_residue: torch.Tensor,
        eps: float = 1e-8,
    ) -> float:
        """
        情報残存率をcosine similarityで評価
        """
        old_norm = torch.norm(old_residue) + eps
        new_norm = torch.norm(new_residue) + eps
        cos_sim = torch.dot(
            old_residue.flatten(), new_residue.flatten()
        ) / (old_norm * new_norm)
        return float(torch.clamp(cos_sim, -1.0, 1.0))


# 簡易テスト
if __name__ == "__main__":
    carry_force_gen = CarryForce(default_persistence=0.88)

    old_r = torch.tensor([0.5, -0.3, 0.7, 0.2])
    # 他のForceからの貢献例
    other_forces = torch.tensor([0.05, 0.1, -0.08, 0.0])

    c_force = carry_force_gen.compute_force(old_r, persistence=0.91)
    print("CarryForce:", c_force)

    # Solver側で合成する例
    new_r = c_force + other_forces
    print("New residue (solver sum):", new_r)

    pers = carry_force_gen.compute_persistence(old_r, new_r)
    print(f"Persistence: {pers:.4f}")
