import numpy as np
import time
import warnings
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ============================================================
# hubCUBE Constraint Layer (Improved v1)
# ============================================================
# 
# デザイン思想:
# - Constraintは状態を持たない純結関数
# - Forceが提案したdeltaを検査・修正し、安全なdeltaのみをSolverに渡す
# - 違反はViolationCollectorに直接emit（Resultオブジェクト生成を避ける）
# - priority: 数値が小さいほど先に適用される（優先度が高い）
# ============================================================


class BaseGeometry:
    def contains(self, position: np.ndarray) -> bool:
        raise NotImplementedError

    def project(self, position: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class SphereGeometry(BaseGeometry):
    """ 球形境界 Geometry 例 ・不変アセットとして使用 """
    def __init__(self, radius: float = 1.0, center: np.ndarray = None):
        self.radius = radius
        self.center = center if center is not None else np.zeros(3)

    def contains(self, position: np.ndarray) -> bool:
        return np.linalg.norm(position - self.center) <= self.radius

    def project(self, position: np.ndarray) -> np.ndarray:
        direction = position - self.center
        dist = np.linalg.norm(direction)
        if dist < 1e-12:  # 数値安定性
            return self.center.copy()
        return self.center + (direction / dist) * self.radius


@dataclass(frozen=True)
class ConstraintViolation:
    constraint_name: str
    source_force: str
    severity: float
    reason: str
    time: float
    position: np.ndarray


class ViolationCollector:
    """ 毎ステップで再利用される違反収集器（アロケーション最小化） """
    def __init__(self):
        self.violations: List[ConstraintViolation] = []

    def emit(self, violation: ConstraintViolation):
        self.violations.append(violation)

    def has_violations(self) -> bool:
        return len(self.violations) > 0

    def clear(self):
        self.violations.clear()


@dataclass(frozen=True)
class ForceOutput:
    delta: np.ndarray
    source: str
    priority: int = 0
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConstraintInput:
    position: np.ndarray
    velocity: np.ndarray
    energy: float
    carry_direction: np.ndarray = field(default_factory=lambda: np.zeros(3))
    # 将来的に CarryForce / RepairForce と連携するための予約フィールド（現在点では未使用）


@dataclass(frozen=True)
class ConstraintConfig:
    max_speed: float = 5.0
    energy_cost_per_unit: float = 1.0
    max_delta: float = 10.0
    active_geometry_key: str = "world_boundary"


@dataclass(frozen=True)
class ConstraintContext:
    dt: float
    step: int
    config: ConstraintConfig
    geometries: Dict[str, BaseGeometry] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegratorInput:
    delta: np.ndarray
    source: str
    violations: List[ConstraintViolation] = field(default_factory=list)


class BaseConstraint:
    """
    Constraintの基底クラス（純結関数として実装）。

    契約:
    - 内部状態を持たない
    - proposed delta を検査・修正して新しい ForceOutput を返す
    - 違反は ViolationCollector に emit する（Result生成を避ける）
    - priority: 数値が小さいほど先に適用される（優先度が高い）
    """
    name: str = "BaseConstraint"
    priority: int = 0

    def apply(
        self,
        input_data: ConstraintInput,
        context: ConstraintContext,
        proposed: ForceOutput,
        collector: Optional[ViolationCollector] = None
    ) -> ForceOutput:
        return proposed


class GeometryConstraint(BaseConstraint):
    name = "GeometryConstraint"
    priority = 10

    def apply(
        self,
        input_data: ConstraintInput,
        context: ConstraintContext,
        proposed: ForceOutput,
        collector: Optional[ViolationCollector] = None
    ) -> ForceOutput:
        geo_key = context.config.active_geometry_key
        geo = context.geometries.get(geo_key)

        if geo is None:
            warnings.warn(
                f"GeometryConstraint: active_geometry_key='{geo_key}' が見つかりません。制約をスキップします。",
                UserWarning,
                stacklevel=2
            )
            return proposed

        next_pos = input_data.position + proposed.delta

        if geo.contains(next_pos):
            return proposed

        # [ねじ曲げないルール]
        # 境界を越えようとした場合、境界上への最短射影位置を計算し、
        # その位置への移動量（legal_delta）に置き換える。
        projected_pos = geo.project(next_pos)
        legal_delta = projected_pos - input_data.position

        if collector is not None:
            collector.emit(ConstraintViolation(
                constraint_name=self.name,
                source_force=proposed.source,
                severity=0.6,
                reason=f"Position breached geometry boundary [{geo_key}]",
                time=context.dt * context.step,
                position=next_pos
            ))

        return ForceOutput(
            delta=legal_delta,
            source=proposed.source,
            priority=proposed.priority,
            weight=proposed.weight,
            metadata=proposed.metadata
        )


class VelocityConstraint(BaseConstraint):
    """
    速度制約。
    GeometryConstraint より後に適用されることを想定（priorityで順序制御）。
    """
    name = "VelocityConstraint"
    priority = 20

    def apply(
        self,
        input_data: ConstraintInput,
        context: ConstraintContext,
        proposed: ForceOutput,
        collector: Optional[ViolationCollector] = None
    ) -> ForceOutput:
        max_speed = context.config.max_speed
        delta_norm = np.linalg.norm(proposed.delta)

        if delta_norm < 1e-12:
            return proposed

        proposed_speed = delta_norm / context.dt

        if proposed_speed > max_speed:
            reduction = max_speed / proposed_speed
            legal_delta = proposed.delta * reduction

            if collector is not None:
                collector.emit(ConstraintViolation(
                    constraint_name=self.name,
                    source_force=proposed.source,
                    severity=0.5,
                    reason=f"Speeding! {proposed_speed:.2f} > Limit: {max_speed}",
                    time=context.dt * context.step,
                    position=input_data.position
                ))
            return ForceOutput(
                delta=legal_delta,
                source=proposed.source,
                priority=proposed.priority,
                weight=proposed.weight,
                metadata=proposed.metadata
            )

        return proposed


class PipelineHook:
    def before_pipeline(self, input_data: ConstraintInput, context: ConstraintContext, proposed: ForceOutput) -> None:
        pass

    def after_pipeline(self, input_data: ConstraintInput, context: ConstraintContext, output: IntegratorInput) -> None:
        pass

    def before_constraint(self, constraint_name: str, input_data: ConstraintInput, proposed: ForceOutput) -> None:
        pass

    def after_constraint(self, constraint_name: str, output: ForceOutput, violated: bool) -> None:
        pass


class MicroProfilerHook(PipelineHook):
    """ 個別Constraintの処理時間をマイクロ秒単位で計測するプロファイラ """
    def __init__(self):
        self.latencies: Dict[str, float] = {}
        self._temp_start: float = 0.0

    def before_constraint(self, constraint_name: str, input_data: ConstraintInput, proposed: ForceOutput) -> None:
        self._temp_start = time.perf_counter_ns()

    def after_constraint(self, constraint_name: str, output: ForceOutput, violated: bool) -> None:
        elapsed_us = (time.perf_counter_ns() - self._temp_start) / 1000.0
        self.latencies[constraint_name] = self.latencies.get(constraint_name, 0.0) + elapsed_us
        if violated:
            print(f"  [Profiler] {constraint_name} が違反を检知! (処理時間: {elapsed_us:.2f} μs)")


class ConstraintPipeline:
    """
    Constraintを優先度順に適用するパイプライン。
    priorityが小さいConstraintから順に適用される。
    Hookによりプロファイリング・拡張が容易。
    """
    def __init__(self, constraints: List[BaseConstraint], hooks: List[PipelineHook] = None):
        self.constraints = sorted(constraints, key=lambda c: c.priority)
        self.hooks = hooks if hooks is not None else []

    def apply_pipeline(
        self,
        input_data: ConstraintInput,
        context: ConstraintContext,
        proposed: ForceOutput,
        collector: ViolationCollector
    ) -> IntegratorInput:

        for hook in self.hooks:
            hook.before_pipeline(input_data, context, proposed)

        current_proposed = proposed

        for constraint in self.constraints:
            for hook in self.hooks:
                hook.before_constraint(constraint.name, input_data, current_proposed)

            before_count = len(collector.violations)
            current_proposed = constraint.apply(input_data, context, current_proposed, collector)
            violated = len(collector.violations) > before_count

            for hook in self.hooks:
                hook.after_constraint(constraint.name, current_proposed, violated)

        integrator_input = IntegratorInput(
            delta=current_proposed.delta,
            source=current_proposed.source,
            violations=collector.violations
        )

        for hook in self.hooks:
            hook.after_pipeline(input_data, context, integrator_input)

        return integrator_input
