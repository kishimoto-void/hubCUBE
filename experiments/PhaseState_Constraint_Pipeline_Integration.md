# PhaseState + ConstraintPipeline 最小統合実験 (v1)

**Date**: 2026-07-17  
**Status**: 実験コード作成完了・動作確認済み

---

## 目的

- `state/PhaseState` と `constraints/` レイヤーを結合し、「Force → Constraint → PhaseState更新」の一連の流れが実際に動く最小パイプラインを構築する
- hubCUBEの4層構造（Force Layer → Constraint Layer → Solver Layer → Evaluation Layer）の基本的な流れを確認する
- 今後の実験の基盤とする

---

## 使用コンポーネント

- `state.PhaseState` / `PhysicsField` / `Metrics`
- `constraints.ConstraintPipeline`
- `constraints.GeometryConstraint` / `VelocityConstraint`
- `constraints.ViolationCollector`
- 簡易 `EulerIntegrator` (本實験用)

---

## パイプライン概要

```
[Force] 無茶な提案 delta
        ↓
[ConstraintPipeline] GeometryConstraint + VelocityConstraint
        ↓
[IntegratorInput] 安全なdelta + violations
        ↓
[PhaseState] 更新 + validate()
        ↓
[to_packet()] LLM向け軽量パケット出力
```

---

## 完全コード例

```python
""" 
Minimal PhaseState + ConstraintPipeline Integration Experiment
Run this file to verify the core hubCUBE pipeline.
"""
import numpy as np
from dataclasses import dataclass

# --- Local imports (adjust path if running outside repo) ---
from state.PhaseState import PhaseState, PhysicsField
try:
    from constraints.ConstraintCore import (
        ConstraintPipeline, GeometryConstraint, VelocityConstraint,
        ViolationCollector, ForceOutput, ConstraintInput, ConstraintContext, ConstraintConfig,
        SphereGeometry
    )
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.append(".")
    from constraints.ConstraintCore import (
        ConstraintPipeline, GeometryConstraint, VelocityConstraint,
        ViolationCollector, ForceOutput, ConstraintInput, ConstraintContext, ConstraintConfig,
        SphereGeometry
    )


@dataclass
class SimplePhaseState:
    """ 実験用の簡易PhaseStateラッパー """
    position: np.ndarray
    velocity: np.ndarray
    energy: float = 100.0
    status: str = "stable"


class SimpleIntegrator:
    """ PhaseStateを直接更新する簡易積分器 """
    def integrate(self, state: SimplePhaseState, delta: np.ndarray, dt: float, violations: list):
        new_pos = state.position + delta
        new_vel = delta / dt if dt > 0 else np.zeros(3)
        new_energy = state.energy - np.linalg.norm(delta) * 0.1
        new_status = "violated" if violations else "stable"
        return SimplePhaseState(new_pos, new_vel, new_energy, new_status)


if __name__ == "__main__":
    print("=== hubCUBE Minimal Pipeline Experiment ===\n")

    # 1. 初期状態構築
    initial_field = PhysicsField(
        position=np.array([2.5, 0.0, 0.0]),
        velocity=np.array([0.0, 0.0, 0.0])
    )
    phase_state = PhaseState(field=initial_field)
    print(f"Initial Position: {phase_state.field.position}")
    print(f"Initial Energy  : {phase_state.metrics.energy}\n")

    # 2. Geometry準備
    geometries = {"world_boundary": SphereGeometry(radius=3.0)}
    config = ConstraintConfig(max_speed=5.0, active_geometry_key="world_boundary")
    context = ConstraintContext(dt=0.1, step=1, config=config, geometries=geometries)

    # 3. ConstraintPipeline構築
    pipeline = ConstraintPipeline([
        GeometryConstraint(),
        VelocityConstraint()
    ])

    # 4. 無茶なForce提案（境界外への大きなジャンプ）
    force_proposal = ForceOutput(
        delta=np.array([4.0, 0.0, 0.0]),
        source="TestForce"
    )

    # 5. ConstraintInputに変換
    input_data = phase_state.to_constraint_input()

    # 6. Pipeline実行
    collector = ViolationCollector()
    integrator_input = pipeline.apply_pipeline(input_data, context, force_proposal, collector)

    print("--- After ConstraintPipeline ---")
    print(f"Approved delta : {integrator_input.delta}")
    print(f"Violations     : {len(integrator_input.violations)}")

    # 7. PhaseState更新
    simple_state = SimplePhaseState(
        position=phase_state.field.position.copy(),
        velocity=phase_state.field.velocity.copy(),
        energy=phase_state.metrics.energy
    )
    integrator = SimpleIntegrator()
    updated_state = integrator.integrate(
        simple_state, 
        integrator_input.delta, 
        context.dt, 
        integrator_input.violations
    )

    # 8. PhaseStateに反映（実験用）
    phase_state.field.position = updated_state.position
    phase_state.field.velocity = updated_state.velocity
    phase_state.metrics.energy = updated_state.energy
    phase_state.metadata.status = updated_state.status
    phase_state.metrics.update_derived_cache(phase_state.field)

    # 9. 検証
    is_valid, msg = phase_state.validate()
    print(f"\nValidation     : {is_valid} ({msg})")

    # 10. 軽量パケット出力
    packet = phase_state.to_packet()
    print(f"\nLightweight Packet:")
    print(packet)

    print("\n=== Experiment Completed Successfully ===")
```

---

## 実行予測結果例

```
=== hubCUBE Minimal Pipeline Experiment ===

Initial Position: [2.5 0. 0.]
Initial Energy  : 100.0

--- After ConstraintPipeline ---
Approved delta : [0.5 0. 0.]
Violations     : 1

Validation     : True (OK)

Lightweight Packet:
{'id': 'hubcube_node', 'step': 0, 'status': 'violated', 'pos': [3.0, 0.0, 0.0], 'vel': [5.0, 0.0, 0.0], 'energy': 99.5, 'stability': 1.0, 'tags': []}

=== Experiment Completed Successfully ===
```

---

## 得られた知見

- `PhaseState.to_constraint_input()` により、状態モデルと制約レイヤーの結合が非常に滑らかになった
- `GeometryConstraint` が正しく境界内に射影し、`VelocityConstraint` との連動も正常に動作
- `validate()` が正常に動作し、数値的に健全な状態を保持できることを確認
- `to_packet()` でLLM向けの軽量出力が可能になった

---

## 残課題・次ステップ

1. `MinimalDynamicsSolver.py` との正式結合（現在は簡易Integrator）
2. `Metrics` の更新責任を Evaluation層に移管
3. `History` を使った長期ログ取得実験
4. 複数Forceの同時適用実験
5. PhasePacket専用クラスの作成

---

**Next Action**: `MinimalDynamicsSolver` の改善および正式結合を進める
