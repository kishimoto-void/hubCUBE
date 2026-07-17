#!/usr/bin/env python3
"""
SimpleDynamicsSolver example (for illustration)

これは説明用の最小ソルバーです。

実際のhubCUBEでは、
Force Modules (CarryForce, BubbleForce, RepairForce...)
Constraint Modules (GeometryConstraint, BoundaryConstraint...)
を合成して新状態を計算します。

状態更新はSolverだけが負う。
"""

import torch
from CarryForce_v4 import CarryForce


def simple_dynamics_solver(
    old_residue: torch.Tensor,
    carry_force: torch.Tensor,
    other_forces: torch.Tensor,
    boundary_limit: float = 3.0,
) -> torch.Tensor:
    """
    最小Dynamics Solver

    - 各Forceをベクトル和
    - Boundary制約を適用 (将来はConstraintモジュールに移行)
    - 新状態を返すのはここだけ
    """
    total_force = carry_force + other_forces
    new_residue = total_force

    # 簡易制約 (Constraint層の代行)
    new_residue = torch.clamp(new_residue, -boundary_limit, boundary_limit)
    return new_residue


if __name__ == "__main__":
    carry_gen = CarryForce(default_persistence=0.87)

    old_r = torch.randn(5) * 0.6
    carry_f = carry_gen.compute_force(old_r, persistence=0.89)

    # 仮の他Force (GeometryやMomentumの代わり)
    other_f = torch.randn(5) * 0.15

    new_r = simple_dynamics_solver(old_r, carry_f, other_f)

    print("Old residue     :", old_r)
    print("CarryForce      :", carry_f)
    print("Other forces    :", other_f)
    print("New residue     :", new_r)
    print("Persistence     :", carry_gen.compute_persistence(old_r, new_r))
