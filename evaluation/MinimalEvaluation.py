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
    Evaluation層の最小オーケストレーター。

    責務:
    - PhaseState.metrics の派生値を再計算させる
    - 計算ロジック本体は Metrics.recompute()に任せる
    - 今後は「何を計測するか」を管理する存在になる予定
    """

    def evaluate(
        self,
        state: PhaseState,
        integrator_input: Optional[IntegratorInput] = None
    ) -> PhaseState:
        """
        Metricsを純結に再計算させる。
        """
        violations = integrator_input.violations if integrator_input else None
        residue = None

        if integrator_input is not None:
            residue = float(np.linalg.norm(integrator_input.delta))

        # Metricsに純結再計算を任せる（メカニカルな方向）
        state.metrics.recompute(
            field=state.field,
            violations=violations,
            residue_norm=residue
        )

        return state


if __name__ == "__main__":
    print("=== MinimalEvaluation (recompute版) Demo ===\n")

    from state.PhaseState import PhysicsField
    from constraints.ConstraintCore import (
        ConstraintPipeline, GeometryConstraint, VelocityConstraint,
        ViolationCollector, ForceOutput, ConstraintContext, ConstraintConfig,
        SphereGeometry
    )
    from dynamics.MinimalDynamicsSolver import MinimalDynamicsSolver

    initial_field = PhysicsField(position=np.array([2.5, 0.0, 0.0]), velocity=np.zeros(3))
    state = PhaseState(field=initial_field)

    geometries = {"world_boundary": SphereGeometry(radius=3.0)}
    config = ConstraintConfig(max_speed=5.0, active_geometry_key="world_boundary")
    context = ConstraintContext(dt=0.1, step=1, config=config, geometries=geometries)

    pipeline = ConstraintPipeline([GeometryConstraint(), VelocityConstraint()])
    force = ForceOutput(delta=np.array([3.8, 0.0, 0.0]), source="TestForce")

    input_data = state.to_constraint_input()
    collector = ViolationCollector()
    integrator_input = pipeline.apply_pipeline(input_data, context, force, collector)

    solver = MinimalDynamicsSolver()
    state = solver.integrate(state, integrator_input, dt=0.1)

    print(f"After Solver  - stability: {state.metrics.stability:.3f}, residue_norm: {state.metrics.residue_norm:.3f}")

    evaluator = MinimalEvaluation()
    state = evaluator.evaluate(state, integrator_input)

    print(f"After Eval    - stability: {state.metrics.stability:.3f}, residue_norm: {state.metrics.residue_norm:.3f}")

    print("\n=== Evaluation (recompute) Test Completed ===")