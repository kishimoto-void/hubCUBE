#!/usr/bin/env python3
"""
MinimalDynamicsSolver v4 - hubCUBEの心臓部（責務境界準拠版）

このバージョンは docs/architecture/Core_Component_Responsibility_Boundaries.md
で定義された原則に基づいて再設計されている。

設計原則（厳守）:
- Solverは状態遷移の「実行（Integrator）」に徹する
- Solverは特定の状態フィールド（residueなど）の意味を知らない
- Forceは「どの対象に、どれだけの変化を望むか」をForceVectorで表現
- Constraintは状態を直接更新せず、判断（Decision）を返す
- 物理法則・更新ロジック・clampなどはSolverに持たせない（可能な限り）
"""

import torch
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ============================================================
# データ構造（境界定義に沿った形）
# ============================================================

@dataclass
class ForceVector:
    """
    Force が表現する「変化の要求」
    Solverはこの情報を使って状態に適用する。
    """
    target: str                 # "residue", "position", "velocity" など
    value: torch.Tensor
    priority: float = 1.0
    source: str = "unknown"
    mode: str = "add"           # 将来的に add / replace / subtract など


@dataclass
class ConstraintDecision:
    """
    Constraint が返す判断
    Solverはこの判断を基に状態遷移を調整する。
    """
    allow: bool = True
    scale: float = 1.0
    reject_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseState:
    """
    Phase 1 時点の最小 PhaseState
    注意: 将来的にはより汎用的な State インターフェースへ移行予定
    """
    position: torch.Tensor
    velocity: torch.Tensor = field(default_factory=lambda: torch.zeros(1))
    energy: float = 0.0
    residue: torch.Tensor = field(default_factory=lambda: torch.zeros(1))
    carry: float = 0.0
    step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolverResult:
    """Solverの出力"""
    new_state: PhaseState
    applied_forces: List[ForceVector]
    decisions: List[ConstraintDecision]
    metrics: Dict[str, float] = field(default_factory=dict)


class MinimalDynamicsSolver:
    """
    最小 Dynamics Solver（Integrator）

    役割を厳密に限定:
    - ForceVector と ConstraintDecision を受け取る
    - 状態遷移を実行して返す（唯一の更新担当）
    - 特定の状態フィールドの意味や物理法則は知らない
    """

    def __init__(self, default_cap: float = 3.0):
        # default_cap は一時的な安全装置。将来的には BoundaryConstraint に移譲
        self.default_cap = default_cap

    def _apply_force_to_state(
        self, state: PhaseState, force: ForceVector
    ) -> PhaseState:
        """
        ForceVector を状態に適用する（現時点の簡易実装）
        将来的にはより抽象的な delta 適用機構に置き換える。
        """
        new_state = state

        if force.target == "residue":
            if force.mode == "add":
                new_residue = state.residue + force.value * force.priority
            else:
                new_residue = force.value * force.priority

            # 一時的な安全クランプ（将来的には削除 or BoundaryConstraint に移譲）
            new_residue = torch.clamp(new_residue, -self.default_cap, self.default_cap)
            new_state = PhaseState(
                position=state.position,
                velocity=state.velocity,
                energy=state.energy,
                residue=new_residue,
                carry=state.carry,
                step=state.step,
                metadata=state.metadata.copy(),
            )

        # 将来的に "position", "velocity" などもここで処理
        return new_state

    def integrate(
        self,
        current_state: PhaseState,
        forces: List[ForceVector],
        decisions: Optional[List[ConstraintDecision]] = None,
    ) -> SolverResult:
        """
        Force と Constraint の判断を基に次の状態を計算する。

        このメソッドは「状態遷移の実行」だけを担当する。
        特定の状態の意味や更新ロジックは知らない。
        """
        decisions = decisions or []
        applied_forces: List[ForceVector] = []

        # 1. Constraint の判断を反映（現時点は簡易 scale）
        scale = 1.0
        for d in decisions:
            if not d.allow:
                scale = 0.0
                break
            scale *= d.scale

        # 2. Force を順次適用
        new_state = current_state
        for f in forces:
            new_state = self._apply_force_to_state(new_state, f)
            applied_forces.append(f)

        # 3. 結果をまとめる
        result = SolverResult(
            new_state=new_state,
            applied_forces=applied_forces,
            decisions=decisions,
            metrics={
                "residue_norm": float(new_state.residue.abs().mean()),
            }
        )

        return result


# ============================================================
# 簡易デモ（Phase 1 実験用）
# ============================================================
if __name__ == "__main__":
    from forces.CarryForce_v4 import CarryForce

    print("=== MinimalDynamicsSolver v4 Demo ===\n")

    solver = MinimalDynamicsSolver(default_cap=3.0)
    carry = CarryForce(default_persistence=0.87)

    state = PhaseState(
        position=torch.zeros(5),
        residue=torch.tensor([0.4, -0.2, 0.6, 0.1, -0.3]),
        carry=0.5,
        step=0,
    )

    for _ in range(5):
        carry_value = carry.compute_force(state.residue, persistence=0.88)

        force_vec = ForceVector(
            target="residue",
            value=carry_value,
            priority=1.0,
            source="CarryForce",
            mode="add",
        )

        result = solver.integrate(
            current_state=state,
            forces=[force_vec],
            decisions=None,
        )

        print(f"Step {result.new_state.step}:")
        print(f"  residue_norm = {result.metrics.get('residue_norm', 0):.4f}")
        print()

        state = result.new_state
