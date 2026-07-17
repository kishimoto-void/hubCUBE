import numpy as np
from typing import Optional

try:
    from state.PhaseState import PhaseState
    from constraints.ConstraintCore import IntegratorInput
except ImportError:
    import sys
    sys.path.append(".")
    from state.PhaseState import PhaseState
    from constraints.ConstraintCore import IntegratorInput


class MinimalEvaluation:
    """
    Evaluation層の最小プロトタイプ。

    責務:
    - PhaseStateの Metrics（派生値）を更新する
    - Solverがやるべきこと（積分）とは嚳密に分離
    - 後続では stability, entropy, oscillation などの計算を強化
    """

    def __init__(self, energy_decay: float = 0.01):
        self.energy_decay = energy_decay

    def evaluate(
        self,
        state: PhaseState,
        integrator_input: Optional[IntegratorInput] = None
    ) -> PhaseState:
        """
        Metricsを更新する。

        現在は最小限の実装:
        - energyの簡易減少
        - residue_normの更新
        - stabilityの簡易計算
        """
        metrics = state.metrics

        # 1. Energyの簡易更新（移動量に応じて減少）
        if integrator_input is not None:
            movement_cost = np.linalg.norm(integrator_input.delta) * 0.05
            metrics.energy = max(0.0, metrics.energy - movement_cost - self.energy_decay)

            # residue_normを更新（最近の移動量から簡易計算）
            metrics.residue_norm = float(np.linalg.norm(integrator_input.delta))

        # 2. Stabilityの簡易計算
        # 違反が多いほど低く、移動が小さいほど高く評価
        violation_penalty = len(integrator_input.violations) * 0.1 if integrator_input else 0.0
        movement_stability = 1.0 / (1.0 + np.linalg.norm(state.field.velocity) * 0.1)
        metrics.stability = max(0.0, min(1.0, movement_stability - violation_penalty))

        # 3. 派生キャッシュの更新
        metrics.update_derived_cache(state.field)

        return state


if __name__ == "__main__":
    print("=== MinimalEvaluation Demo ===\n")

    from state.PhaseState import PhysicsField
    from constraints.ConstraintCore import (
        ConstraintPipeline, GeometryConstraint, VelocityConstraint,
        ViolationCollector, ForceOutput, ConstraintContext, ConstraintConfig,
        SphereGeometry
    )
    from dynamics.MinimalDynamicsSolver import MinimalDynamicsSolver

    # 初期状態
    initial_field = PhysicsField(position=np.array([2.5, 0.0, 0.0]), velocity=np.zeros(3))
    state = PhaseState(field=initial_field)

    # Pipeline
    geometries = {"world_boundary": SphereGeometry(radius=3.0)}
    config = ConstraintConfig(max_speed=5.0, active_geometry_key="world_boundary")
    context = ConstraintContext(dt=0.1, step=1, config=config, geometries=geometries)

    pipeline = ConstraintPipeline([GeometryConstraint(), VelocityConstraint()])
    force = ForceOutput(delta=np.array([3.5, 0.0, 0.0]), source="TestForce")

    input_data = state.to_constraint_input()
    collector = ViolationCollector()
    integrator_input = pipeline.apply_pipeline(input_data, context, force, collector)

    # Solver
    solver = MinimalDynamicsSolver()
    state = solver.integrate(state, integrator_input, dt=0.1)

    print(f"After Solver - Energy: {state.metrics.energy:.2f}, Stability: {state.metrics.stability:.3f}")

    # Evaluation
    evaluator = MinimalEvaluation()
    state = evaluator.evaluate(state, integrator_input)

    print(f"After Evaluation - Energy: {state.metrics.energy:.2f}, Stability: {state.metrics.stability:.3f}")
    print(f"residue_norm: {state.metrics.residue_norm:.4f}")

    print("\n=== Evaluation Test Completed ===")