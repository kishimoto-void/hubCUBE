#!/usr/bin/env python3
"""
hubCUBE SingleRoleCUBE Template v4 - ForceBased

CarryForce を実際に compose した最新推奨テンプレート。

設計原則:
- Carry は Force のみ生成（状態更新は Solver / ここでは observe_step で合成）
- 他の Force（Geometry, Momentum など）は将来的に独立モジュールとして追加可能
- persistence は cosine similarity で評価
"""

import torch
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import math
from collections import deque

from CarryForce_v4 import CarryForce


torch.manual_seed(42)


@dataclass
class BaseCUBEState:
    axis: torch.Tensor
    residue: torch.Tensor
    tension: torch.Tensor
    status: Dict[str, float]
    links: List[Tuple[int, int, float]]
    step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaseMetrics:
    anomaly_score: float
    is_anomaly: bool
    residue_norm: float
    coherence: float
    entropy: float
    num_links: int
    sustained_score: float = 0.0
    carry_persistence: float = 0.0
    role_specific: Dict[str, Any] = field(default_factory=dict)


class SingleRoleCUBE:
    """
    v4 ForceBased 基底
    - CarryForce を内部で使用
    - 必要に応じて他の Force を合成可能
    """

    def __init__(
        self,
        role_name: str = "GenericObserver",
        num_positions: int = 5,
        default_persistence: float = 0.87,
        link_threshold: float = 0.15,
        anomaly_threshold: float = 0.48,
        residue_cap: float = 3.0,
    ):
        self.role_name = role_name
        self.num_positions = num_positions
        self.link_threshold = link_threshold
        self.anomaly_threshold = anomaly_threshold
        self.residue_cap = residue_cap

        self.carry_force = CarryForce(default_persistence=default_persistence)

        self.res_history: deque = deque(maxlen=12)
        self.ema_res = 0.0
        self.anomaly_duration = 0

    def create_initial_state(self) -> BaseCUBEState:
        return BaseCUBEState(
            axis=torch.zeros(self.num_positions),
            residue=torch.zeros(self.num_positions),
            tension=torch.zeros(self.num_positions),
            status={"phase": 0.0, "coherence": 0.82, "entropy": 0.18},
            links=[],
            metadata={}
        )

    def _update_common_metrics(self, res_norm: float) -> float:
        self.res_history.append(res_norm)
        alpha = 0.2
        self.ema_res = (1 - alpha) * self.ema_res + alpha * res_norm
        return sum(self.res_history) / max(1, len(self.res_history))

    def build_links(self, values: torch.Tensor) -> List[Tuple[int, int, float]]:
        # 簡易リンク生成（Observation層の責務として残す）
        if self.num_positions < 2:
            return []
        diff = values.unsqueeze(1) - values.unsqueeze(0)
        strength = (diff.abs() * 0.7 + values.abs().unsqueeze(1) * 0.3)
        triu = torch.triu_indices(self.num_positions, self.num_positions, offset=1)
        strengths = strength[triu[0], triu[1]]
        mask = strengths > self.link_threshold
        idx = triu[:, mask]
        return [(int(idx[0,i]), int(idx[1,i]), round(float(strengths[mask][i]),3))
                for i in range(mask.sum())][:4]

    def _compute_forces(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, float]:
        """
        Force 合成層（ここで複数の Force を組み合わせる）
        現在は CarryForce のみ。将来的に GeometryForce, MomentumForce などを追加。
        """
        val = float(x.mean()) if x.numel() > 1 else float(x)
        proj = torch.zeros(self.num_positions)
        mid = self.num_positions // 2
        proj[mid] = val * 0.6
        if mid > 0: proj[mid-1] = val * 0.2
        if mid < self.num_positions-1: proj[mid+1] = val * 0.2

        new_axis = state.axis * 0.55 + proj * 0.45
        delta = new_axis - state.axis

        # CarryForce から力を取得
        carry_f = self.carry_force.compute_force(
            state.residue,
            persistence=self.carry_force.default_persistence
        )

        # 将来的に他の Force をここで合成
        # geometry_f = geometry_force.compute(...)
        # momentum_f = momentum_force.compute(...)
        other_forces = delta * 0.8   # 暫定的に delta を other force として扱う

        total_force = carry_f + other_forces

        # 簡易 persistence 計算（Solver 的に new を仮定して評価）
        tentative_new = torch.clamp(total_force, -self.residue_cap, self.residue_cap)
        persistence = self.carry_force.compute_persistence(state.residue, tentative_new)

        return total_force, new_axis, persistence

    def observe_step(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[BaseCUBEState, BaseMetrics]:
        total_force, new_axis, persistence = self._compute_forces(state, x)

        new_res = torch.clamp(total_force, -self.residue_cap, self.residue_cap)

        # Tension は Force の結果から簡易計算
        new_ten = (new_res - state.residue).abs() * 0.6 + state.tension * 0.4

        res_m = float(new_res.abs().mean())
        sustained = self._update_common_metrics(res_m)

        new_links = self.build_links(new_res)
        new_status = state.status.copy()
        new_status["coherence"] = max(0.25, new_status.get("coherence", 0.82) - res_m * 0.7)
        new_status["entropy"] = min(1.2, new_status.get("entropy", 0.18) + res_m * 0.5)

        anomaly_score = min(1.0, res_m * 2.5 + sustained * 1.4)
        is_anomaly = anomaly_score > self.anomaly_threshold
        self.anomaly_duration = self.anomaly_duration + 1 if is_anomaly else 0

        new_state = BaseCUBEState(
            axis=new_axis, residue=new_res, tension=new_ten,
            status=new_status, links=new_links, step=state.step + 1,
            metadata=state.metadata
        )

        metrics = BaseMetrics(
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            residue_norm=round(res_m, 4),
            coherence=round(new_status["coherence"], 3),
            entropy=round(new_status["entropy"], 3),
            num_links=len(new_links),
            sustained_score=round(sustained, 4),
            carry_persistence=round(persistence, 4),
        )
        return new_state, metrics


class CUBEHub:
    def __init__(self, name: str = "MainHub"):
        self.name = name
        self.cubes: Dict[str, SingleRoleCUBE] = {}
        self.states: Dict[str, BaseCUBEState] = {}

    def register(self, cube: SingleRoleCUBE):
        self.cubes[cube.role_name] = cube
        self.states[cube.role_name] = cube.create_initial_state()

    def observe_all(self, x: torch.Tensor) -> Dict[str, BaseMetrics]:
        results = {}
        for name, cube in self.cubes.items():
            new_state, metrics = cube.observe_step(self.states[name], x)
            self.states[name] = new_state
            results[name] = metrics
        return results


if __name__ == "__main__":
    print("hubCUBE v4 ForceBased Demo")
    hub = CUBEHub()
    hub.register(SingleRoleCUBE(role_name="TestObserver", num_positions=5))

    for i in range(6):
        x = torch.tensor([0.6 + 0.3 * (i % 3 - 1)])
        res = hub.observe_all(x)
        m = res["TestObserver"]
        print(f"Step {i+1}: res_norm={m.residue_norm:.4f} persistence={m.carry_persistence:.3f}")
