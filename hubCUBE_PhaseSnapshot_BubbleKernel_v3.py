#!/usr/bin/env python3
"""
hubcube_bubble_core_v3.py
PhaseSnapshot を用いた完全イミュータブルな状態遷移カーネル
≬ プロトコルによる泛用力学系抽象化実装
"""

import numpy as np
from dataclasses import dataclass, field, replace
from typing import List, Dict, Any, Tuple, Protocol
from types import MappingProxyType
import json


# ============================================================
# ≡ 【不変構造：Frozen Component Layer】
# ============================================================

@dataclass(frozen=True)
class PhysicsField:
    position: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self):
        pos = np.asarray(self.position, dtype=np.float64).copy()
        vel = np.asarray(self.velocity, dtype=np.float64).copy()
        acc = np.asarray(self.acceleration, dtype=np.float64).copy()
        pos.flags.writeable = False
        vel.flags.writeable = False
        acc.flags.writeable = False
        object.__setattr__(self, "position", pos)
        object.__setattr__(self, "velocity", vel)
        object.__setattr__(self, "acceleration", acc)


@dataclass(frozen=True)
class Carry:
    last_delta: np.ndarray = field(default_factory=lambda: np.zeros(3))
    momentum: np.ndarray = field(default_factory=lambda: np.zeros(3))
    payload: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self):
        ld = np.asarray(self.last_delta, dtype=np.float64).copy()
        mm = np.asarray(self.momentum, dtype=np.float64).copy()
        ld.flags.writeable = False
        mm.flags.writeable = False
        object.__setattr__(self, "last_delta", ld)
        object.__setattr__(self, "momentum", mm)


@dataclass(frozen=True)
class Metrics:
    energy: float = 0.0
    entropy: float = 0.0
    stability: float = 1.0
    oscillation: float = 0.0
    residue_norm: float = 0.0
    velocity_norm: float = 0.0


@dataclass(frozen=True)
class Metadata:
    step: int = 0
    time: float = 0.0
    status: str = "stable"


@dataclass(frozen=True)
class PhaseSnapshot:
    """完全イミュータブルな状態スナップショット（状態遷移カーネル専用）"""
    field: PhysicsField
    carry: Carry = field(default_factory=Carry)
    metrics: Metrics = field(default_factory=Metrics)
    metadata: Metadata = field(default_factory=Metadata)


# ============================================================
# ≬ 【構造同型：Abstract Protocol Layer】
# ============================================================

@dataclass(frozen=True)
class PotentialCenter:
    """純綜几何座標と強度のみを保持（意味論的トレースなし）"""
    position: np.ndarray
    intensity: float
    radius: float
    is_attraction: bool
    force_id: str

    def __post_init__(self):
        pos = np.asarray(self.position, dtype=np.float64).copy()
        pos.flags.writeable = False
        object.__setattr__(self, "position", pos)


class ForceModel(Protocol):
    """≬ 任意の力学系（重力・電磁気・泡・社会的フォース等）と合同であれば置換可能"""
    def compute_acceleration(self, pos: np.ndarray, vel: np.ndarray, centers: List[PotentialCenter]) -> np.ndarray:
        ...

    def compute_potential(self, pos: np.ndarray, centers: List[PotentialCenter]) -> float:
        ...


class ConstraintModel(Protocol):
    """≬ 任意の几何境界（球・立方体・トーラス等）と合同であれば置換可能"""
    def enforce(self, pos: np.ndarray, vel: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, bool]:
        ...


# ============================================================
# ＝ 【決定積分：Deterministic Integration Layer】 (RK4)
# ============================================================

class RK4DynamicsSolver:
    """
    純綜なRK4時間積分のみを担当。
    エネルギー計算や意味的評価は一切行わず、位置・速度の几何更新に徹する。
    """
    def __init__(self, force_model: ForceModel, constraint_model: ConstraintModel):
        self.force = force_model
        self.constraint = constraint_model

    def step(self, snapshot: PhaseSnapshot, centers: List[PotentialCenter], dt: float) -> Tuple[PhaseSnapshot, float]:
        x0 = snapshot.field.position
        v0 = snapshot.field.velocity

        # RK4 stages (正しい状態更新)
        f1 = self.force.compute_acceleration(x0, v0, centers)
        k1_x = v0
        k1_v = f1

        x2 = x0 + 0.5 * dt * k1_x
        v2 = v0 + 0.5 * dt * k1_v
        f2 = self.force.compute_acceleration(x2, v2, centers)
        k2_x = v2
        k2_v = f2

        x3 = x0 + 0.5 * dt * k2_x
        v3 = v0 + 0.5 * dt * k2_v
        f3 = self.force.compute_acceleration(x3, v3, centers)
        k3_x = v3
        k3_v = f3

        x4 = x0 + dt * k3_x
        v4 = v0 + dt * k3_v
        f4 = self.force.compute_acceleration(x4, v4, centers)
        k4_x = v4
        k4_v = f4

        # 最終更新
        next_x = x0 + (dt / 6.0) * (k1_x + 2 * k2_x + 2 * k3_x + k4_x)
        next_v = v0 + (dt / 6.0) * (k1_v + 2 * k2_v + 2 * k3_v + k4_v)

        # 速度上限クリップ
        v_norm = np.linalg.norm(next_v)
        if v_norm > 6.5:
            next_v = (next_v / v_norm) * 6.5

        # 几何拘束適用
        pos, vel, residue, violated = self.constraint.enforce(next_x, next_v)

        next_snapshot = replace(
            snapshot,
            field=PhysicsField(position=pos, velocity=vel, acceleration=f1),
            carry=Carry(
                last_delta=pos - x0,
                momentum=0.8 * snapshot.carry.momentum + 0.2 * vel,
                payload=snapshot.carry.payload
            ),
            metadata=Metadata(
                step=snapshot.metadata.step + 1,
                time=snapshot.metadata.time + dt,
                status="violated" if violated else "stable"
            )
        )
        return next_snapshot, residue


# ============================================================
# ≠ 【散逸評価：Statistical Evaluation Layer】
# ============================================================

class PureNumericalEvaluator:
    """ソルバーから分離された純綜評価層。エネルギー・散逸統計を非破壊的に算出"""
    @staticmethod
    def evaluate(snapshot: PhaseSnapshot, force_model: ForceModel, centers: List[PotentialCenter], residue: float) -> PhaseSnapshot:
        field_data = snapshot.field
        carry_data = snapshot.carry

        v_norm = float(np.linalg.norm(field_data.velocity))
        d_norm = float(np.linalg.norm(carry_data.last_delta))

        # Energy
        potential_energy = force_model.compute_potential(field_data.position, centers)
        kinetic_energy = 0.5 * 1.0 * (v_norm ** 2)
        total_energy = kinetic_energy + potential_energy

        # Stability
        stability_score = max(0.0, 1.0 - ((residue * 0.5) + (v_norm / 15.0)))

        # Entropy (方向の不整合)
        if d_norm > 1e-5 and v_norm > 1e-5:
            cos_theta = np.dot(carry_data.last_delta, field_data.velocity) / (d_norm * v_norm)
            entropy_score = float(0.5 * (1.0 - cos_theta))
        else:
            entropy_score = 0.0

        # Oscillation
        proposed_d = field_data.velocity
        p_norm = float(np.linalg.norm(proposed_d))
        if d_norm > 1e-5 and p_norm > 1e-5:
            dot_val = np.dot(carry_data.last_delta, proposed_d) / (d_norm * p_norm)
            osc_detect = 1.0 if dot_val < -0.2 else 0.0
            oscillation_score = 0.7 * snapshot.metrics.oscillation + 0.3 * osc_detect
        else:
            oscillation_score = snapshot.metrics.oscillation

        return replace(snapshot, metrics=Metrics(
            energy=total_energy,
            entropy=entropy_score,
            stability=stability_score,
            oscillation=oscillation_score,
            residue_norm=residue,
            velocity_norm=v_norm
        ))


# ============================================================
# 📦 【Pipeline & Serializer】
# ============================================================

class PhaseRegistry:
    def __init__(self):
        self.snapshots: List[PhaseSnapshot] = []

    def register(self, snapshot: PhaseSnapshot):
        self.snapshots.append(snapshot)

    def step_pipeline(self, solver: RK4DynamicsSolver, force_model: ForceModel,
                      centers: List[PotentialCenter], dt: float):
        for i, current in enumerate(self.snapshots):
            integrated, residue = solver.step(current, centers, dt)
            self.snapshots[i] = PureNumericalEvaluator.evaluate(integrated, force_model, centers, residue)


class LLMPacketBuilder:
    @staticmethod
    def build_packet(registry: PhaseRegistry) -> Dict[str, Any]:
        nodes = []
        for snap in registry.snapshots:
            nodes.append({
                "node_id": snap.carry.payload.get("source_id", "unnamed_node"),
                "step": snap.metadata.step,
                "status": snap.metadata.status,
                "pos": [round(float(x), 4) for x in snap.field.position],
                "vel": [round(float(x), 4) for x in snap.field.velocity],
                "metrics": {
                    "energy": round(snap.metrics.energy, 4),
                    "velocity_norm": round(snap.metrics.velocity_norm, 4),
                    "stability": round(snap.metrics.stability, 4),
                    "entropy": round(snap.metrics.entropy, 4),
                    "oscillation": round(snap.metrics.oscillation, 4),
                    "residue": round(snap.metrics.residue_norm, 4)
                },
                "semantic_anchor": snap.carry.payload.get("semantic_role", "none")
            })

        total_energy = sum(n["metrics"]["energy"] for n in nodes)
        avg_stability = sum(n["metrics"]["stability"] for n in nodes) / max(1, len(nodes))

        return {
            "protocol": "hubcube_v3.0_frozen_snapshot_kernel",
            "system_metrics": {
                "total_nodes": len(nodes),
                "global_net_energy": round(total_energy, 4),
                "global_mean_stability": round(avg_stability, 4)
            },
            "packet_stream": nodes
        }


# ============================================================
# 🔮 【具象実装例：BubbleForceModel & SphericalConstraint】
# ============================================================

class BubbleForceModel:
    """フォースモデルプロトコルを満たす泡力学の実装（Morseポテンシャル + 非保存摩擩 + ドリフト）"""
    def __init__(self, damping: float = 0.35, drift_k: float = 0.09):
        self.global_damping = damping
        self.drift_k = drift_k

    def _compute_morse_grad(self, pos: np.ndarray, center: PotentialCenter) -> Tuple[float, np.ndarray]:
        to_c = pos - center.position
        d = np.linalg.norm(to_c) + 1e-8
        De = center.intensity

        if center.is_attraction:
            a = 1.4
            r0 = center.radius
            exp_term = np.exp(-a * (d - r0))
            v = De * ((1.0 - exp_term) ** 2) - De
            grad_scalar = 2.0 * a * De * (1.0 - exp_term) * exp_term
            grad = grad_scalar * (to_c / d)
        else:
            sigma = center.radius * 0.65
            v = De * np.exp(-d / sigma)
            grad = -v * (1.0 / sigma) * (to_c / d)
        return v, grad

    def compute_acceleration(self, pos: np.ndarray, vel: np.ndarray, centers: List[PotentialCenter]) -> np.ndarray:
        f_cons = np.zeros(3)
        for c in centers:
            _, grad_v = self._compute_morse_grad(pos, c)
            f_cons += -grad_v

        # 非保存回転摩擩（直交成分を強調）
        v_norm = np.linalg.norm(vel)
        f_c_norm = np.linalg.norm(f_cons)
        if v_norm > 1e-3 and f_c_norm > 1e-3:
            f_non_ortho = f_cons - np.dot(f_cons, vel / v_norm) * (vel / v_norm)
            f_cons += -f_non_ortho * 1.1

        return f_cons - self.global_damping * vel + (np.zeros(3) - pos) * self.drift_k

    def compute_potential(self, pos: np.ndarray, centers: List[PotentialCenter]) -> float:
        total_v = 0.0
        for c in centers:
            v_val, _ = self._compute_morse_grad(pos, c)
            total_v += v_val
        return total_v


class SphericalConstraintModel:
    """コンストレイントモデルプロトコルを満たす球形境界"""
    def __init__(self, radius: float = 4.5):
        self.radius = radius

    def enforce(self, pos: np.ndarray, vel: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, bool]:
        dist = np.linalg.norm(pos)
        if dist <= self.radius:
            return pos, vel, 0.0, False

        normal = pos / (dist + 1e-9)
        corrected_pos = normal * self.radius
        residue = float(np.linalg.norm(pos - corrected_pos))

        v_n = np.dot(vel, normal)
        corrected_vel = vel - v_n * normal * 1.15 if v_n > 0 else vel
        return corrected_pos, corrected_vel, residue, True


# ============================================================
# 実行テスト（忠実な実験実行）
# ============================================================
if __name__ == "__main__":
    print("=== hubCUBE Bubble Particle v3 忠実実行テスト ===\n")

    # 1. ≬ プロトコル準拠コンポーネントの構築
    bubble_physics = BubbleForceModel(damping=0.35, drift_k=0.09)
    sphere_boundary = SphericalConstraintModel(radius=4.5)
    core_solver = RK4DynamicsSolver(force_model=bubble_physics, constraint_model=sphere_boundary)

    # 2. 力場設定（1吸引 + 1斥力）
    centers = [
        PotentialCenter(np.array([-1.5, -0.5, 0.0]), intensity=4.0, radius=2.0, is_attraction=True, force_id="f_001"),
        PotentialCenter(np.array([1.5, 0.5, 0.0]), intensity=4.5, radius=1.5, is_attraction=False, force_id="f_002")
    ]

    # 3. 初期Snapshot登録（完全凍結ペイロード）
    registry = PhaseRegistry()
    raw_payload = {"source_id": "agent_alpha_01", "semantic_role": "explorer"}
    registry.register(PhaseSnapshot(
        field=PhysicsField(position=[2.0, 0.0, -0.5], velocity=[-1.0, 2.0, 0.5]),
        carry=Carry(payload=MappingProxyType(raw_payload))
    ))

    print("初期状態登録完了。3ステップの時間発展を開始します...\n")

    # 4. パイプライン実行（3ステップ）
    for step in range(3):
        registry.step_pipeline(core_solver, bubble_physics, centers, dt=0.08)
        snap = registry.snapshots[-1]
        print(f"Step {snap.metadata.step}: "
              f"pos=({snap.field.position[0]:.3f}, {snap.field.position[1]:.3f}, {snap.field.position[2]:.3f}) | "
              f"energy={snap.metrics.energy:.4f} | stability={snap.metrics.stability:.4f} | "
              f"residue={snap.metrics.residue_norm:.6f}")

    print("\n=== LLM向けパケット出力 ===\n")
    packet = LLMPacketBuilder.build_packet(registry)
    print(json.dumps(packet, indent=2, ensure_ascii=False))
