#!/usr/bin/env python3
"""
CUBE Anomaly Detection System v2.6 (Robust & Explainable)
- 改善①: 指数関数によるスコア飽和の防止
- 改善②: MAD (Median Absolute Deviation) による頑健な動的閾値
- 改善③: 残溜時経列のコサイン類似度による異常伝播リンク生成
- 改善④: Soft Vote (重み付き連続値平均) による統合診断
- 改善⑤: メタデータのライフサイクル完全対応
"""

import torch
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from collections import deque

torch.manual_seed(42)

# ============================================================
# ①～⑤に対応したデータクラスの拡張
# ============================================================
@dataclass
class CUBEMetadata:
    timestamp: float = 0.0
    source: str = "unknown"
    sensor_id: str = "default_sensor"
    confidence_gate: float = 1.0
    extra_info: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BaseCUBEState:
    axis: torch.Tensor
    residue: torch.Tensor
    tension: torch.Tensor
    status: Dict[str, float]
    links: List[Tuple[int, int, float]]
    step: int = 0
    metadata: CUBEMetadata = field(default_factory=CUBEMetadata)

@dataclass
class BaseMetrics:
    anomaly_score: float
    is_anomaly: bool
    dynamic_threshold: float
    root_causes: List[int]
    residue_norm: float
    coherence: float
    entropy: float
    num_links: int
    sustained_score: float = 0.0
    ema_residue: float = 0.0
    anomaly_duration: int = 0
    role_specific: Dict[str, Any] = None


# ============================================================
# 改良版 SingleRoleCUBE
# ============================================================
class SingleRoleCUBE:
    """ 単一役割CUBE ロバスト診断型（v2.6） """
    
    def __init__(
        self,
        role_name: str = "Generic",
        num_positions: int = 5,
        residue_decay: float = 0.87,
        link_threshold: float = 0.40,  # コサイン類似度用に閾値を調整
        initial_anomaly_threshold: float = 0.35,
        residue_cap: float = 5.0,
        nsigma: float = 3.0,           # MADに対する倍率
        window_size: int = 10          # リンク計算用の残溜時経列ウィンドウサイズ
    ):
        self.role_name = role_name
        self.num_positions = num_positions
        self.residue_decay = residue_decay
        self.link_threshold = link_threshold
        self.residue_cap = residue_cap
        self.nsigma = nsigma
        self.window_size = window_size
        
        # 統計推移バッファ
        self.res_history: deque = deque(maxlen=15)
        self.score_history: deque = deque(maxlen=40)  # MAD計算用に少し長めに確保
        
        # 改善③: ポジションごとの残溜時経列を記録するテンソルバッファ (window_size, num_positions)
        self.residue_window = torch.zeros(self.window_size, self.num_positions)
        
        self.ema_res = 0.0
        self.ema_ten = 0.0
        self.anomaly_duration = 0
        self.current_threshold = initial_anomaly_threshold

    def create_initial_state(self, metadata: Optional[CUBEMetadata] = None) -> BaseCUBEState:
        # 改善⑤: メタデータの初期化対応
        return BaseCUBEState(
            axis=torch.zeros(self.num_positions),
            residue=torch.zeros(self.num_positions),
            tension=torch.zeros(self.num_positions),
            status={"phase": 0.0, "coherence": 1.0, "entropy": 0.0},
            links=[],
            metadata=metadata if metadata is not None else CUBEMetadata()
        )

    def _update_stats_and_threshold_mad(self, score: float, res_norm: float, ten_norm: float) -> float:
        """ 改善②: MADを用いたロバストな動的閾値更新 """
        self.res_history.append(res_norm)
        self.score_history.append(score)
        
        alpha = 0.2
        self.ema_res = (1 - alpha) * self.ema_res + alpha * res_norm
        self.ema_ten = (1 - alpha) * self.ema_ten + alpha * ten_norm
        
        # 過去スコアが留積されたらMADベースで計算
        if len(self.score_history) >= 15:
            scores_tensor = torch.tensor(list(self.score_history))
            median = scores_tensor.median()
            # Median Absolute Deviation の計算
            mad = (scores_tensor - median).abs().median()
            
            # 正規分布の一致性因子 1.4826 を使用。MADが0になるのを防ぐため下限を設定
            robust_std = 1.4826 * max(mad.item(), 0.01)
            target_th = median.item() + self.nsigma * robust_std
            
            # 急激な変化を防ぐEMAスムージング
            self.current_threshold = 0.95 * self.current_threshold + 0.05 * target_th
            
        return sum(self.res_history) / max(1, len(self.res_history))

    def _isolate_root_causes(self, residue: torch.Tensor, tension: torch.Tensor) -> List[int]:
        contribution = residue.abs() * 0.6 + tension * 0.4
        
        # 原因特定側にもロバスト性を入れるためmedianベースで判定
        med = contribution.median()
        mad = (contribution - med).abs().median()
        threshold = med + 2.0 * max(1.4826 * mad, 0.1)
        
        causes = (contribution > threshold).nonzero(as_tuple=True)[0].tolist()
        return causes

    def build_links_cosine(self, current_step: int) -> List[Tuple[int, int, float]]:
        """ 改善③: 各ポジションの残溜時経列挙動のコサイン類似度から『異常伝播グラフ』を構筑 """
        if current_step < self.window_size or self.num_positions < 2:
            return []
            
        # テンソルの形状: (window_size, num_positions) -> 転置して (num_positions, window_size)
        # 各ポジションの過去の「動きのベクトル」を取得
        pos_vectors = self.residue_window.t()
        
        # L2ノルムで正規化 (ゼロ除算対策)
        norms = pos_vectors.norm(dim=1, keepdim=True)
        norms = torch.where(norms == 0, torch.ones_like(norms), norms)
        normalized_vectors = pos_vectors / norms
        
        # 全ペアのコサイン類似度行列を一括計算 (num_positions, num_positions)
        cosine_matrix = torch.mm(normalized_vectors, normalized_vectors.t())
        
        # 上三角行列を取得（自己ループと重複ペアを排除）
        triu_indices = torch.triu_indices(self.num_positions, self.num_positions, offset=1)
        sims = cosine_matrix[triu_indices[0], triu_indices[1]]
        
        mask = sims > self.link_threshold
        filtered_indices = triu_indices[:, mask]
        filtered_sims = sims[mask]
        
        new_links = []
        for idx in range(filtered_sims.size(0)):
            i = int(filtered_indices[0, idx])
            j = int(filtered_indices[1, idx])
            w = float(filtered_sims[idx])
            new_links.append((i, j, round(w, 3)))
            
        return sorted(new_links, key=lambda x: x[2], reverse=True)[:4]

    def _update_status(self, status: Dict[str, float], res_m: float, ten_m: float) -> Dict[str, float]:
        new_status = status.copy()
        new_status["phase"] = (new_status["phase"] + 0.05) % (2 * math.pi)
        new_status["coherence"] = max(0.01, min(1.0, new_status["coherence"] - ten_m * 0.4))
        new_status["entropy"] = max(0.0, min(2.0, new_status["entropy"] + res_m * 0.3))
        return new_status

    def _compute_core(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        new_axis = state.axis * 0.7 + x * 0.3
        new_res = torch.clamp(
            state.residue * self.residue_decay + (x - state.axis),
            -self.residue_cap, self.residue_cap
        )
        new_ten = (new_res - state.residue).abs()
        return new_axis, new_res, new_ten, {}

    def observe_step(self, state: BaseCUBEState, x: torch.Tensor, next_metadata: Optional[CUBEMetadata] = None) -> Tuple[BaseCUBEState, BaseMetrics]:
        # 1. コア計算
        new_axis, new_res, new_ten, role_specific = self._compute_core(state, x)
        
        # 改善③: 残溜の時経列ウィンドウをローリング更新
        self.residue_window = torch.cat([self.residue_window[1:], new_res.unsqueeze(0)], dim=0)
        
        res_m = float(new_res.abs().mean())
        ten_m = float(new_ten.mean())
        
        # 改善①: 指数関数を用いた飽和しないスコアリング (k=1.8でスケーリング)
        linear_sum = res_m * 2.2 + ten_m * 1.5
        anomaly_score = 1.0 - math.exp(-1.8 * linear_sum)
        
        # 改善②: MADベースの動的閾値と統計の更新
        sustained = self._update_stats_and_threshold_mad(anomaly_score, res_m, ten_m)
        
        # 最終異常判定
        is_anomaly = anomaly_score > self.current_threshold
        self.anomaly_duration = self.anomaly_duration + 1 if is_anomaly else 0
        
        # 原因特定とコサイン類似度リンクの構筑
        root_causes = self._isolate_root_causes(new_res, new_ten) if is_anomaly else []
        new_links = self.build_links_cosine(state.step + 1)
        
        new_status = self._update_status(state.status, res_m, ten_m)
        
        # 改善⑤: メタデータの継続・更新処理
        current_meta = next_metadata if next_metadata is not None else state.metadata

        new_state = BaseCUBEState(
            axis=new_axis, residue=new_res, tension=new_ten,
            status=new_status, links=new_links, step=state.step + 1,
            metadata=current_meta
        )
        
        metrics = BaseMetrics(
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            dynamic_threshold=round(self.current_threshold, 4),
            root_causes=root_causes,
            residue_norm=round(res_m, 4),
            coherence=round(new_status["coherence"], 3),
            entropy=round(new_status["entropy"], 3),
            num_links=len(new_links),
            sustained_score=round(sustained, 4),
            ema_residue=round(self.ema_res, 4),
            anomaly_duration=self.anomaly_duration,
            role_specific=role_specific
        )
        
        return new_state, metrics


# ============================================================
# 改良版 CUBEHub（Soft Vote & Dynamic Decision）
# ============================================================
class CUBEHub:
    """ 改善④: コヒーレンス加重Soft Voteによる統合診断マネージャ """
    
    def __init__(self, global_threshold: float = 0.35):
        self.cubes: Dict[str, SingleRoleCUBE] = {}
        self.states: Dict[str, BaseCUBEState] = {}
        self.global_metrics: Dict[str, Any] = {}
        self.global_threshold = global_threshold
    
    def register(self, cube: SingleRoleCUBE, initial_metadata: Optional[CUBEMetadata] = None):
        self.cubes[cube.role_name] = cube
        self.states[cube.role_name] = cube.create_initial_state(metadata=initial_metadata)
    
    def observe_all(self, x: torch.Tensor, next_metadata: Optional[CUBEMetadata] = None) -> Dict[str, BaseMetrics]:
        results = {}
        weighted_score_sum = 0.0
        total_weight = 0.0
        all_root_causes = []

        for name, cube in self.cubes.items():
            current_state = self.states[name]
            
            # 改善⑤: メタデータを各CUBEのステップへ伝播
            next_state, metrics = cube.observe_step(current_state, x, next_metadata=next_metadata)
            self.states[name] = next_state
            results[name] = metrics
            
            # 各CUBEの内的コヒーレンスを重みとする
            weight = max(0.01, current_state.status["coherence"])
            
            # 改善④: Soft Vote (スコアの加重連続値)
            weighted_score_sum += metrics.anomaly_score * weight
            total_weight += weight
            
            if metrics.is_anomaly:
                all_root_causes.extend(metrics.root_causes)
                
        # 統合スコアの算出
        global_score = weighted_score_sum / total_weight if total_weight > 0 else 0.0
        global_anomaly = global_score > self.global_threshold
        
        # 複数観点から共通して指摘された原因の抽出
        most_frequent_causes = list(set([c for c in all_root_causes if all_root_causes.count(c) >= max(1, len(self.cubes)//2)]))
        
        self.global_metrics["global_score"] = round(global_score, 4)
        self.global_metrics["global_anomaly"] = global_anomaly
        self.global_metrics["global_root_causes"] = sorted(most_frequent_causes) if global_anomaly else []
        
        # 改善⑤: 最新のメタデータをHubのグローバル空間へ記録
        self.global_metrics["last_metadata"] = next_metadata.__dict__ if next_metadata else {}
        
        return results


# ============================================================
# 動作検証
# ============================================================
if __name__ == "__main__":
    import time
    
    hub = CUBEHub(global_threshold=0.40)
    
    # 改善⑤: コンテキスト情報付きのメタデータを生成
    init_meta = CUBEMetadata(source="edge_node_alpha", sensor_id="sensor_xyz_01")
    
    hub.register(SingleRoleCUBE(role_name="FastAdaptObserver", num_positions=5, residue_decay=0.70), initial_metadata=init_meta)
    hub.register(SingleRoleCUBE(role_name="SlowAdaptObserver", num_positions=5, residue_decay=0.95), initial_metadata=init_meta)
    
    # 1. 正常ストリームでのMAD動的閾値の慫らし駆動（25ステップ）
    for step in range(25):
        normal_input = torch.randn(5) * 0.15
        current_meta = CUBEMetadata(timestamp=time.time(), source="edge_node_alpha", sensor_id="sensor_xyz_01")
        hub.observe_all(normal_input, next_metadata=current_meta)
        
    print("--- 正常フェーズ完了（MAD閾値の安定化） ---")
    
    # 2. 境界線上のグレーな異常を注入（Soft Voteの検証用）
    # 0 or 1判定だと弾かれるかもしれない絶妙なノイズ
    gray_input = torch.randn(5) * 0.15
    gray_input[1] += 0.85 
    gray_input[4] += 0.90
    
    current_meta = CUBEMetadata(timestamp=time.time(), source="edge_node_alpha", sensor_id="sensor_xyz_01", extra_info={"phase": "test_gray"})
    step_metrics = hub.observe_all(gray_input, next_metadata=current_meta)
    
    print(f"\n[グレーノイズ注入時のHub診断]")
    print(f"Global Score: {hub.global_metrics['global_score']} (Threshold: {hub.global_threshold})")
    print(f"Global Anomaly: {hub.global_metrics['global_anomaly']}")
    
    # 3. 巨大なスパイク異常を注入（コサイン類似度・伝播の検証用）
    # ポジション 2 と 3 を同期させて激しく掺らす
    print("\n--- 巨大同期スパイク注入（3ステップ持続） ---")
    for spike_step in range(3):
        spike_input = torch.randn(5) * 0.15
        spike_input[2] += 5.0
        spike_input[3] += 5.0  # 2と3が同じ挙動で破壊される
        
        current_meta = CUBEMetadata(timestamp=time.time(), source="edge_node_alpha", sensor_id="sensor_xyz_01", extra_info={"spike_idx": spike_step})
        step_metrics = hub.observe_all(spike_input, next_metadata=current_meta)
        
    # 最終ステップのリンク（伝播）を確認
    print(f"\n[巨大スパイク後のHub診断]")
    print(f"Global Anomaly: {hub.global_metrics['global_anomaly']}")
    print(f"Global Root Causes (原因ポジション): {hub.global_metrics['global_root_causes']}")
    
    print(f"\n[FastAdaptObserverのコサイン類似度リンク(異常伝播)]")
    # 2と3が同期して動いたため、(2, 3)の類似度が高くなる
    for link in hub.states["FastAdaptObserver"].links:
        print(f"  ポジション {link[0]} ── ポジション {link[1]} (類似度: {link[2]})")
