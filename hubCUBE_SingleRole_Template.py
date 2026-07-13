#!/usr/bin/env python3
"""
hubCUBE - SingleRoleCUBE Template v2
ヨール固定型CUBEアーキテクチャの汎用テンプレート

設計思想:
- 1 CUBE = 1 役割（完全特化）
- 共通処理（EMA, links生成, status更新, キャッピング）を基底に集約
- Event Hook（before/after）で拡張易
- CUBEHubで複数CUBEを疎結合統合
"""

import torch
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import math
from collections import deque

torch.manual_seed(42)


# ============================================================
# 共通データ構造
# ============================================================
@dataclass
class BaseCUBEState:
    axis: torch.Tensor
    residue: torch.Tensor
    tension: torch.Tensor
    status: Dict[str, float]
    links: List[Tuple[int, int, float]]
    step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)   # 役割固有データ


@dataclass
class BaseMetrics:
    anomaly_score: float
    is_anomaly: bool
    residue_norm: float
    coherence: float
    entropy: float
    num_links: int
    sustained_score: float = 0.0
    ema_residue: float = 0.0
    anomaly_duration: int = 0
    role_specific: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# SingleRoleCUBE 基底クラス（v2）
# ============================================================
class SingleRoleCUBE:
    """
    単一役割CUBEの基底クラス
    - 共通ライフサイクル・メトリクス更新をここに集約
    - 役割特化ロジックは observe_step をオーバーライドして実装
    """

    def __init__(
        self,
        role_name: str = "GenericObserver",
        num_positions: int = 5,
        residue_decay: float = 0.87,
        link_threshold: float = 0.15,
        anomaly_threshold: float = 0.48,
        residue_cap: float = 3.0,
    ):
        self.role_name = role_name
        self.num_positions = num_positions
        self.residue_decay = residue_decay
        self.link_threshold = link_threshold
        self.anomaly_threshold = anomaly_threshold
        self.residue_cap = residue_cap

        # 共通状態管理
        self.res_history: deque = deque(maxlen=12)
        self.ema_res = 0.0
        self.ema_ten = 0.0
        self.anomaly_duration = 0

    def create_initial_state(self) -> BaseCUBEState:
        """ 役割に応じてオーバーライド推奨 """
        return BaseCUBEState(
            axis=torch.zeros(self.num_positions),
            residue=torch.zeros(self.num_positions),
            tension=torch.zeros(self.num_positions),
            status={"phase": 0.0, "coherence": 0.82, "entropy": 0.18},
            links=[],
            metadata={}
        )

    # ==================== 共通ヘルパーメソッド ====================
    def update_common_metrics(self, res_norm: float, ten_norm: float) -> float:
        """EMA + 持続性スコアの共通更新"""
        self.res_history.append(res_norm)
        alpha = 0.2
        self.ema_res = (1 - alpha) * self.ema_res + alpha * res_norm
        self.ema_ten = (1 - alpha) * self.ema_ten + alpha * ten_norm
        sustained = sum(self.res_history) / max(1, len(self.res_history))
        return sustained

    def build_links(self, values: torch.Tensor) -> List[Tuple[int, int, float]]:
        """ 残溜・緊張に基づく可変連結の共通生成 """
        new_links: List[Tuple[int, int, float]] = []
        for i in range(self.num_positions):
            for j in range(i + 1, self.num_positions):
                strength = abs(float(values[i] - values[j])) * 0.65 + float(values[i].abs()) * 0.35
                strength = max(0.0, min(1.0, strength))
                if strength > self.link_threshold:
                    new_links.append((i, j, round(strength, 3)))
        return sorted(new_links, key=lambda x: x[2], reverse=True)[:4]

    def update_status(
        self,
        status: Dict[str, float],
        res_m: float,
        ten_m: float,
        phase_d: float = 0.0
    ) -> Dict[str, float]:
        """statusの共通更新"""
        status["phase"] = (status.get("phase", 0.0) + phase_d) % (2 * math.pi)
        status["coherence"] = max(0.25, status.get("coherence", 0.82) - ten_m * 0.8)
        status["entropy"] = min(1.2, status.get("entropy", 0.18) + res_m * 0.6)
        return status

    def clamp_residue(self, res: torch.Tensor) -> torch.Tensor:
        """ 残溜キャッピング（長期留積防止） """
        return torch.clamp(res, -self.residue_cap, self.residue_cap)

    # ==================== Event Hooks ====================
    def before_observe_step(self, state: BaseCUBEState, x: torch.Tensor):
        """ ステップ前処理（ログ・同期・前処理用にオーバーライド） """
        pass

    def after_observe_step(self, state: BaseCUBEState, metrics: BaseMetrics):
        """ ステップ後処理（後処理・通知用にオーバーライド） """
        pass

    # ==================== メイン処理（役割特化はここをオーバーライド） ====================
    def observe_step(
        self, state: BaseCUBEState, x: torch.Tensor
    ) -> Tuple[BaseCUBEState, BaseMetrics]:
        """
        役割特化ロジックを実装するメインエントリポイント。
        サブクラスでオーバーライドしてください。
        ここでは最小限の共通処理のみ。
        """
        self.before_observe_step(state, x)

        # 簡易軸投影（実際は役割ごとに大きく変える）
        val = float(x.mean()) if x.numel() > 1 else float(x)
        proj = torch.zeros(self.num_positions)
        mid = self.num_positions // 2
        proj[mid] = val * 0.6
        if mid > 0:
            proj[mid - 1] = val * 0.2
        if mid < self.num_positions - 1:
            proj[mid + 1] = val * 0.2

        new_axis = state.axis * 0.55 + proj * 0.45
        new_res = self.clamp_residue(
            state.residue * self.residue_decay + (new_axis - state.axis)
        )

        # Tension簡易計算
        d = new_res[1:] - new_res[:-1]
        new_ten = torch.zeros_like(new_res)
        new_ten[:-1] += d.abs() * 0.5
        new_ten[1:] += d.abs() * 0.5

        res_m = float(new_res.abs().mean())
        ten_m = float(new_ten.mean())

        # 共通メトリクス更新
        sustained = self.update_common_metrics(res_m, ten_m)

        # リンク生成
        new_links = self.build_links(new_res)

        # ステータス更新
        new_status = self.update_status(state.status.copy(), res_m, ten_m)

        # 異常スコア（EMA + 持続性重視）
        anomaly_score = min(1.0, res_m * 2.8 + sustained * 1.6 + ten_m * 1.0)
        is_anomaly = anomaly_score > self.anomaly_threshold
        self.anomaly_duration = self.anomaly_duration + 1 if is_anomaly else 0

        new_state = BaseCUBEState(
            axis=new_axis,
            residue=new_res,
            tension=new_ten,
            status=new_status,
            links=new_links,
            step=state.step + 1,
            metadata=state.metadata,
        )

        metrics = BaseMetrics(
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            residue_norm=round(res_m, 4),
            coherence=round(new_status["coherence"], 3),
            entropy=round(new_status["entropy"], 3),
            num_links=len(new_links),
            sustained_score=round(sustained, 4),
            ema_residue=round(self.ema_res, 4),
            anomaly_duration=self.anomaly_duration,
        )

        self.after_observe_step(new_state, metrics)
        return new_state, metrics

    # ==================== 運用支援メソッド ====================
    def reset_residue(self, state: BaseCUBEState, strength: float = 1.0) -> BaseCUBEState:
        """ 外部から残溜をリセット """
        if hasattr(state, "residue"):
            state.residue = state.residue * (1.0 - strength) * 0.3
            state.residue = self.clamp_residue(state.residue)
        self.res_history.clear()
        self.ema_res = 0.0
        self.anomaly_duration = 0
        return state

    def inject_tension(self, state: BaseCUBEState, position: int, amount: float) -> BaseCUBEState:
        """ 外部刺激としてtensionを注入 """
        if 0 <= position < len(state.tension):
            state.tension[position] += amount
        return state


# ============================================================
# CUBE Hub（複数CUBEの統合層）
# ============================================================
class CUBEHub:
    """
    複数のSingleRoleCUBEを束ねて統合判断を行う上位層
    各CUBEは独立して観測し、Hubが結果を統合
    """

    def __init__(self, name: str = "MainHub"):
        self.name = name
        self.cubes: Dict[str, SingleRoleCUBE] = {}
        self.states: Dict[str, BaseCUBEState] = {}
        self.history: List[Dict[str, Any]] = []

    def register(self, cube: SingleRoleCUBE, initial_state: Optional[BaseCUBEState] = None):
        self.cubes[cube.role_name] = cube
        if initial_state is None:
            initial_state = cube.create_initial_state()
        self.states[cube.role_name] = initial_state

    def observe_all(self, x: torch.Tensor) -> Dict[str, BaseMetrics]:
        results = {}
        for role_name, cube in self.cubes.items():
            state = self.states[role_name]
            new_state, metrics = cube.observe_step(state, x)
            self.states[role_name] = new_state
            results[role_name] = metrics

        # 統合判断の例（必要に応じて拡張）
        total_anomaly = any(m.is_anomaly for m in results.values())
        self.history.append({
            "step": len(self.history),
            "results": {k: m.anomaly_score for k, m in results.items()},
            "global_anomaly": total_anomaly
        })
        return results

    def reset_all(self):
        for role_name, cube in self.cubes.items():
            self.states[role_name] = cube.reset_residue(self.states[role_name])
        self.history.clear()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "hub_name": self.name,
            "registered_roles": list(self.cubes.keys()),
            "total_steps": len(self.history),
            "last_global_anomaly": self.history[-1]["global_anomaly"] if self.history else False
        }


# ============================================================
# 使用例（ResidueObserverCUBEの実装例）
# ============================================================
class ResidueObserverCUBE(SingleRoleCUBE):
    """ 残溜観測に完全特化したCUBE（改善版） """

    def __init__(self, **kwargs):
        super().__init__(role_name="ResidueObserver", **kwargs)

    def observe_step(self, state: BaseCUBEState, x: torch.Tensor):
        # 役割特化ロジック + 共通処理を組み合わせる場合の例
        # ここでは基底の共通処理を活用しつつ、必要なら拡張
        return super().observe_step(state, x)


if __name__ == "__main__":
    print("=" * 80)
    print("hubCUBE SingleRole Template v2 - Demo")
    print("=" * 80)

    # Hub作成
    hub = CUBEHub("TestHub")

    # CUBE登録
    res_cube = ResidueObserverCUBE(anomaly_threshold=0.45, residue_cap=2.5)
    hub.register(res_cube)

    # 観測実行
    for i in range(7):
        x = torch.tensor([0.7 + 0.3 * (i % 3 - 1)])
        results = hub.observe_all(x)
        m = results["ResidueObserver"]
        print(f"Step {i+1}: anomaly={m.anomaly_score:.3f} | sustained={m.sustained_score:.3f} | is_anomaly={m.is_anomaly}")

    print("\nHub Summary:", hub.get_summary())
    print("=" * 80)