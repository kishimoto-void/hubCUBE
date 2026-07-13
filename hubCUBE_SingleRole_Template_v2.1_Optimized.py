#!/usr/bin/env python3
"""
CUBE Single Role Template v2.1 (Optimized)
- 共通処理のTemplate Method化
- PyTorchテンソル演算によるリンク生成の高速化
- CUBEHubの状態管理を完全補完
"""

import torch
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
import math
from collections import deque

torch.manual_seed(42)

# ============================================================
# 共通データクラス
# ============================================================
@dataclass
class BaseCUBEState:
    axis: torch.Tensor
    residue: torch.Tensor
    tension: torch.Tensor
    status: Dict[str, float]
    links: List[Tuple[int, int, float]]
    step: int = 0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

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
    role_specific: Dict[str, Any] = None

# ============================================================
# 基底クラス（共通処理を集約・プロセスの統制）
# ============================================================
class SingleRoleCUBE:
    """ 単一役割CUBE基底クラス（v2.1） """
    
    def __init__(
        self,
        role_name: str = "Generic",
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
        
        self.res_history: deque = deque(maxlen=12)
        self.ema_res = 0.0
        self.ema_ten = 0.0
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

    def _update_common_metrics(self, res_norm: float, ten_norm: float) -> float:
        """EMA・持続性スコアの更新"""
        self.res_history.append(res_norm)
        alpha = 0.2
        self.ema_res = (1 - alpha) * self.ema_res + alpha * res_norm
        self.ema_ten = (1 - alpha) * self.ema_ten + alpha * ten_norm
        return sum(self.res_history) / max(1, len(self.res_history))

    def build_links(self, values: torch.Tensor) -> List[Tuple[int, int, float]]:
        """ テンソル演算を用いて可変連結を高速生成 (O(N^2)のPythonループを排除) """
        if self.num_positions < 2:
            return []

        # ペア間の差分行列を計算: diff[i, j] = values[i] - values[j]
        diff = values.unsqueeze(1) - values.unsqueeze(0)
        
        # 各要素の絶対値（自身）の貢獻: shape (N, 1) -> ブロードキャストで各ペアに適用
        abs_i = values.abs().unsqueeze(1)
        
        # 強度行列の一括計算
        strength_matrix = diff.abs() * 0.7 + abs_i * 0.3
        
        # 上三角行列のみを取得（自己参照および重複ペアを排除）
        triu_indices = torch.triu_indices(self.num_positions, self.num_positions, offset=1)
        strengths = strength_matrix[triu_indices[0], triu_indices[1]]
        
        # 閾値判定
        mask = strengths > self.link_threshold
        filtered_indices = triu_indices[:, mask]
        filtered_strengths = strengths[mask]
        
        # 結果の構筑
        new_links = []
        for idx in range(filtered_strengths.size(0)):
            i = int(filtered_indices[0, idx])
            j = int(filtered_indices[1, idx])
            w = float(filtered_strengths[idx])
            new_links.append((i, j, round(w, 3)))
            
        return sorted(new_links, key=lambda x: x[2], reverse=True)[:4]

    def _update_status(self, status: Dict[str, float], res_m: float, ten_m: float, phase_d: float = 0.0) -> Dict[str, float]:
        new_status = status.copy()
        new_status["phase"] = (new_status["phase"] + phase_d) % (2 * math.pi)
        new_status["coherence"] = max(0.25, new_status["coherence"] - ten_m * 0.8)
        new_status["entropy"] = min(1.2, new_status["entropy"] + res_m * 0.6)
        return new_status

    # ==================== Event Hooks ====================
    def before_observe_step(self, state: BaseCUBEState, x: torch.Tensor):
        pass

    def after_observe_step(self, state: BaseCUBEState, metrics: BaseMetrics):
        pass

    # ==================== 役割特化ロジック用フック ====================
    def _compute_core(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        """
        派生クラスでオーバーライドするコアロジック。
        デフォルトではシンプルな更新を行う。
        Returns: (new_axis, new_residue, new_tension, role_specific_metrics)
        """
        new_axis = state.axis * 0.6 + x.mean() * 0.4
        new_res = torch.clamp(
            state.residue * self.residue_decay + (new_axis - state.axis),
            -self.residue_cap, self.residue_cap
        )
        new_ten = (new_res - state.residue).abs() # 前ステップからの変化量をtensionとする例
        return new_axis, new_res, new_ten, {}

    # ==================== メインパイプライン ====================
    def observe_step(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[BaseCUBEState, BaseMetrics]:
        """ パイプラインの統制（Template Method） """
        self.before_observe_step(state, x)
        
        # 1. 役割特化コア計算の呼び出し
        new_axis, new_res, new_ten, role_specific = self._compute_core(state, x)
        
        # 2. 共通メトリクス評価
        res_m = float(new_res.abs().mean())
        ten_m = float(new_ten.mean())
        sustained = self._update_common_metrics(res_m, ten_m)
        
        # 3. 状態更新とリンク構筑
        new_links = self.build_links(new_res)
        new_status = self._update_status(state.status, res_m, ten_m)
        
        # 4. 異常检知スコアリング
        anomaly_score = min(1.0, res_m * 2.8 + sustained * 1.6)
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
            ema_residue=round(self.ema_res, 4),
            anomaly_duration=self.anomaly_duration,
            role_specific=role_specific
        )
        
        self.after_observe_step(new_state, metrics)
        return new_state, metrics


# ============================================================
# CUBE Hub（状態管理の完全自動化）
# ============================================================
class CUBEHub:
    """ 複数のSingleRoleCUBEを管理し、統合的に推理を実行するマネージャ層 """
    
    def __init__(self):
        self.cubes: Dict[str, SingleRoleCUBE] = {}
        self.states: Dict[str, BaseCUBEState] = {}
        self.global_metrics: Dict[str, Any] = {}
    
    def register(self, cube: SingleRoleCUBE):
        self.cubes[cube.role_name] = cube
        self.states[cube.role_name] = cube.create_initial_state()
    
    def observe_all(self, x: torch.Tensor) -> Dict[str, BaseMetrics]:
        results = {}
        for name, cube in self.cubes.items():
            current_state = self.states[name]
            # 各CUBEのステップを実行して状態を内部更新
            next_state, metrics = cube.observe_step(current_state, x)
            self.states[name] = next_state
            results[name] = metrics
            
        # 統合判断ロジック（例：過半数のCUBEで異常が検知されたか）
        anomalies = [m.is_anomaly for m in results.values()]
        self.global_metrics["global_anomaly"] = sum(anomalies) > (len(self.cubes) / 2) if anomalies else False
        
        return results


# ============================================================
# 使用例（固有ロジックの実装方法）
# ============================================================
class ResidueObserverCUBE(SingleRoleCUBE):
    def __init__(self, **kwargs):
        super().__init__(role_name="ResidueObserver", **kwargs)
    
    def _compute_core(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        """ 役割特化ロジックのみを綺麗に記述 """
        # 例: 残溜(Residue)の変動に対してより敏感に反応する固有ロジック
        new_axis = state.axis * 0.5 + x * 0.5
        new_res = torch.clamp(
            state.residue * self.decay_factor_custom(state.step) + (new_axis - state.axis),
            -self.residue_cap, self.residue_cap
        )
        new_ten = (new_res - state.residue).abs() * 1.2
        
        # 固有メトリクス
        role_specific = {"max_residue_index": int(new_res.abs().argmax())}
        
        return new_axis, new_res, new_ten, role_specific

    def decay_factor_custom(self, step: int) -> float:
        return self.residue_decay * (1.0 - 0.01 * math.sin(step / 10.0))


# ============================================================
# 動作検証用エントリポイント
# ============================================================
if __name__ == "__main__":
    hub = CUBEHub()
    hub.register(ResidueObserverCUBE(num_positions=5))
    hub.register(SingleRoleCUBE(role_name="GenericObserver", num_positions=5))
    
    # 模激入力ストリームの入力
    for step in range(3):
        mock_input = torch.randn(5) * (2.0 if step == 2 else 0.5) # ステップ 2 で異常をシミュレート
        print(f"\n--- Step {step} ---")
        step_metrics = hub.observe_all(mock_input)
        for role, metric in step_metrics.items():
            print(f"[{role}] Anomaly Score: {metric.anomaly_score} (Is Anomaly: {metric.is_anomaly}), Links: {metric.num_links}")
        print(f"Global Anomaly Status: {hub.global_metrics.get('global_anomaly')}")
