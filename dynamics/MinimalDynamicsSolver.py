import numpy as np
from typing import Optional

try:
    from state.PhaseState import PhaseState
    from constraints.ConstraintCore import IntegratorInput
except ImportError:
    # Fallback for standalone testing
    import sys
    sys.path.append(".")
    from state.PhaseState import PhaseState
    from constraints.ConstraintCore import IntegratorInput


class MinimalDynamicsSolver:
    """
    hubCUBEの心臓部（Integrator）。

    責務を嚳密に限定した最小実装:
    - IntegratorInput（安全なdelta + violations）を受け取る
    - PhaseStateを直接更新する（唯一の状態更新担当）
    - 積分（position, velocity）のみを担当
    - Evaluation層がやるべきこと（energy, stability等）は行わない
    """

    def integrate(
        self,
        state: PhaseState,
        integrator_input: IntegratorInput,
        dt: float,
        debug: bool = False
    ) -> PhaseState:
        """
        PhaseStateを更新する。

        Args:
            state: 更新対象の PhaseState
            integrator_input: ConstraintPipelineからの出力（安全化済みdelta + violations）
            dt: タイムステップ
            debug: Trueの時のみ validate()を実行（パフォーマンス配慮）
        """
        delta = integrator_input.delta

        # 1. 積分（Solverの主な責務）
        state.field.position = state.field.position + delta
        state.field.velocity = delta / dt if dt > 0 else np.zeros(3)

        # 2. 違反情報に基づくステータス更新（最小限）
        if integrator_input.violations:
            state.metadata.status = "violated"
        else:
            state.metadata.status = "stable"

        # 3. 派生キャッシュの更新
        state.metrics.update_derived_cache(state.field)

        # 4. デバッグ時のみ検証（大規模シミュレーションでは重いのでオプション）
        if debug:
            is_valid, msg = state.validate()
            if not is_valid:
                print(f"[MinimalDynamicsSolver] Validation failed: {msg}")

        return state


# ============================================================
# 簡易テスト（実験用）
# ============================================================
if __name__ == "__main__":
    print("=== MinimalDynamicsSolver Improved Demo ===\n")

    from state.PhaseState import PhysicsField
    from constraints.ConstraintCore import (
        ConstraintPipeline, GeometryConstraint, VelocityConstraint,
        ViolationCollector, ForceOutput, ConstraintContext, ConstraintConfig,
        SphereGeometry, IntegratorInput
    )

    # 初期状態
    initial_field = PhysicsField(
        position=np.array([2.5, 0.0, 0.0]),
        velocity=np.array([0.0, 0.0, 0.0])
    )
    state = PhaseState(field=initial_field)

    # Geometry準備
    geometries = {"world_boundary": SphereGeometry(radius=3.0)}
    config = ConstraintConfig(max_speed=5.0, active_geometry_key="world_boundary")
    context = ConstraintContext(dt=0.1, step=1, config=config, geometries=geometries)

    # Pipeline
    pipeline = ConstraintPipeline([GeometryConstraint(), VelocityConstraint()])

    # 無茶なForce提案
    force_proposal = ForceOutput(delta=np.array([4.0, 0.0, 0.0]), source="TestForce")

    # ConstraintInputに変換
    input_data = state.to_constraint_input()

    # Pipeline実行
    collector = ViolationCollector()
    integrator_input = pipeline.apply_pipeline(input_data, context, force_proposal, collector)

    print(f"Approved delta: {integrator_input.delta}")
    print(f"Violations    : {len(integrator_input.violations)}\n")

    # Solver実行
    solver = MinimalDynamicsSolver()
    updated_state = solver.integrate(state, integrator_input, dt=0.1, debug=True)

    print(f"New Position : {updated_state.field.position}")
    print(f"New Velocity : {updated_state.field.velocity}")
    print(f"Status       : {updated_state.metadata.status}")
    print(f"Energy       : {updated_state.metrics.energy:.2f}")

    print("\n=== Solver Test Completed ===")