#!/usr/bin/env python3
"""
MinimalDynamicsSolver v1 - hubCUBEの心臓部

設計原則（最優先で守る）:
- Solverだけが状態を更新する
- Forceは「力ベクトル」のみ返す（状態更新をしない）
- Constraintは「制約」のみ返す（状態更新をしない）
- これらを合成して新PhaseStateを生成する唯一の場所

Phase 1 の最初の本格実装として、CarryForce と最小Constraintを
受け取って次の状態を計算する最小形を提供する。
"""

import torch
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any


@dataclass
class PhaseState:
    """
    hubCUBE の基本 PhaseState（Phase 1 版）

    将来的には state/PhaseState.py に移動・拡張予定。
    """
    position: torch.Tensor
    velocity: torch.Tensor = field(default_factory=lambda: torch.zeros(1))
    energy: float = 0.0
    residue: torch.Tensor = field(default_factory=lambda: torch.zeros(1))
    carry: float = 0.0
    step: int = 0
    history: List[float] = field(default_factory=list)
    waypoint: Optional[torch.Tensor] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MinimalDynamicsSolver:
    """
    最小 Dynamics Solver

    役割:
    - 複数の Force から total_force を合成
    - Constraint を適用
    - 新しい PhaseState を生成して返す（唯一の状態更新担当）
    """

    def __init__(self, residue_cap: float = 3.0):
        self.residue_cap = residue_cap

    def integrate(
        self,
        current_state: PhaseState,
        forces: List[torch.Tensor],
        constraints: Optional[List[Callable[[torch.Tensor], torch.Tensor]]] = None,
    ) -> PhaseState:
        """
        Force と Constraint を統合して次の状態を計算

        Args:
            current_state: 現在の PhaseState
            forces: 各 Force モジュールから返された力のリスト
            constraints: 制約関数（状態を受け取り、制約適用後の状態を返す）のリスト

        Returns:
            新しい PhaseState（Solver だけがこれを生成する）
        """
        # 1. Force の合成
        if forces:
            total_force = torch.stack(forces).sum(dim=0)
        else:
            total_force = torch.zeros_like(current_state.residue)

        # 2. 仮の新 residue を計算（まだ制約前）
        new_residue = current_state.residue + total_force

        # 3. Constraint の適用（存在する場合）
        if constraints:
            for constraint_fn in constraints:
                new_residue = constraint_fn(new_residue)

        # 4. 基本的なクランプ（将来的には BoundaryConstraint に移譲）
        new_residue = torch.clamp(new_residue, -self.residue_cap, self.residue_cap)

        # 5. 簡易 velocity / energy 更新（PhaseState の拡張分）
        new_velocity = new_residue - current_state.residue
        new_energy = current_state.energy + float(new_residue.abs().mean()) * 0.1

        # 6. 新しい PhaseState を生成（ここが唯一の状態更新ポイント）
        new_state = PhaseState(
            position=current_state.position + new_velocity * 0.5,  # 簡易移動
            velocity=new_velocity,
            energy=new_energy,
            residue=new_residue,
            carry=current_state.carry * 0.95 + float(new_residue.abs().mean()) * 0.05,
            step=current_state.step + 1,
            history=current_state.history + [float(new_residue.abs().mean())],
            waypoint=current_state.waypoint,
            metadata=current_state.metadata.copy(),
        )

        return new_state


# ============================================================
# 簡易動作確認用デモ（Phase 1 実験用）
# ============================================================
if __name__ == "__main__":
    from forces.CarryForce_v4 import CarryForce

    print("=== MinimalDynamicsSolver v1 Demo ===\n")

    solver = MinimalDynamicsSolver(residue_cap=3.0)
    carry = CarryForce(default_persistence=0.87)

    # 初期状態
    state = PhaseState(
        position=torch.zeros(5),
        residue=torch.tensor([0.4, -0.2, 0.6, 0.1, -0.3]),
        carry=0.5,
        step=0,
    )

    for step in range(5):
        # CarryForce から力を取得
        carry_force = carry.compute_force(state.residue, persistence=0.88)

        # Solver に渡して次の状態を得る
        new_state = solver.integrate(
            current_state=state,
            forces=[carry_force],
            constraints=None,  # Phase 1 ではまだ Constraint なし
        )

        print(f"Step {new_state.step}:")
        print(f"  residue_norm = {new_state.residue.abs().mean():.4f}")
        print(f"  energy       = {new_state.energy:.4f}")
        print(f"  carry        = {new_state.carry:.4f}")
        print()

        state = new_state
