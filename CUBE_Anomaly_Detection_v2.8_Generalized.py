#!/usr/bin/env python3
"""
CUBE Anomaly Detection System v2.8 (Generalized Consistency Checker)

レビュー提案を反映した汎用性向上版

新規機能:
- 入力標準化 (Z-score 風) のオプション支援
- 異常伝播リンクを使った根本原因トリアージ (上流優先)
- スケール不一致・連鎖現象への対応性向上
"""

import torch
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from collections import deque

torch.manual_seed(42)


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


class SingleRoleCUBE:
    """ 単一役割CUBE v2.8 (汎用性向上版) """
    
    def __init__(
        self,
        role_name: str = "Generic",
        num_positions: int = 5,
        residue_decay: float = 0.87,
        link_threshold: float = 0.40,
        initial_anomaly_threshold: float = 0.35,
        residue_cap: float = 5.0,
        nsigma: float = 3.0,
        window_size: int = 10,
        root_cause_nsigma: float = 2.0,
        normalize_input: bool = False,      # 新規: 入力標準化オプション
        norm_method: str = "zscore",        # "zscore" or "minmax"
    ):
        self.role_name = role_name
        self.num_positions = num_positions
        self.residue_decay = residue_decay
        self.link_threshold = link_threshold
        self.residue_cap = residue_cap
        self.nsigma = nsigma
        self.window_size = window_size
        self.root_cause_nsigma = root_cause_nsigma
        self.normalize_input = normalize_input
        self.norm_method = norm_method
        
        self.res_history: deque = deque(maxlen=15)
        self.score_history: deque = deque(maxlen=40)
        self.residue_window = torch.zeros(self.window_size, self.num_positions)
        
        # 標準化用統計量
        self.input_mean = torch.zeros(num_positions)
        self.input_std = torch.ones(num_positions)
        self.input_min = torch.zeros(num_positions)
        self.input_max = torch.ones(num_positions)
        self.norm_count = 0
        
        self.ema_res = 0.0
        self.ema_ten = 0.0
        self.anomaly_duration = 0
        self.current_threshold = initial_anomaly_threshold

    def _normalize(self, x: torch.Tensor) -> torch.Tensor:
        """ 入力の標準化 (running Z-score or Min-Max) """
        if not self.normalize_input:
            return x
        
        self.norm_count += 1
        alpha = 0.1  # running average の学習率
        
        if self.norm_method == "zscore":
            if self.norm_count == 1:
                self.input_mean = x.clone()
                self.input_std = torch.ones_like(x) * 0.1
            else:
                self.input_mean = (1 - alpha) * self.input_mean + alpha * x
                self.input_std = (1 - alpha) * self.input_std + alpha * (x - self.input_mean).abs()
            
            std_safe = torch.where(self.input_std < 1e-6, torch.ones_like(self.input_std), self.input_std)
            return (x - self.input_mean) / std_safe
        
        elif self.norm_method == "minmax":
            if self.norm_count == 1:
                self.input_min = x.clone()
                self.input_max = x.clone()
            else:
                self.input_min = torch.minimum(self.input_min, x)
                self.input_max = torch.maximum(self.input_max, x)
            
            range_safe = torch.where((self.input_max - self.input_min) < 1e-6, 
                                     torch.ones_like(self.input_max), 
                                     self.input_max - self.input_min)
            return (x - self.input_min) / range_safe
        
        return x

    def create_initial_state(self, metadata: Optional[CUBEMetadata] = None) -> BaseCUBEState:
        return BaseCUBEState(
            axis=torch.zeros(self.num_positions),
            residue=torch.zeros(self.num_positions),
            tension=torch.zeros(self.num_positions),
            status={"phase": 0.0, "coherence": 1.0, "entropy": 0.0},
            links=[],
            metadata=metadata if metadata is not None else CUBEMetadata()
        )

    def _update_stats_and_threshold_mad(self, score: float, res_norm: float, ten_norm: float) -> float:
        self.res_history.append(res_norm)
        self.score_history.append(score)
        
        alpha = 0.2
        self.ema_res = (1 - alpha) * self.ema_res + alpha * res_norm
        self.ema_ten = (1 - alpha) * self.ema_ten + alpha * ten_norm
        
        if len(self.score_history) >= 15:
            scores_tensor = torch.tensor(list(self.score_history))
            median = scores_tensor.median()
            mad = (scores_tensor - median).abs().median()
            robust_std = 1.4826 * max(mad.item(), 0.01)
            target_th = median.item() + self.nsigma * robust_std
            self.current_threshold = 0.95 * self.current_threshold + 0.05 * target_th
            
        return sum(self.res_history) / max(1, len(self.res_history))

    def _isolate_root_causes(self, residue: torch.Tensor, tension: torch.Tensor, links: List[Tuple[int, int, float]] = None) -> List[int]:
        contribution = residue.abs() * 0.6 + tension * 0.4
        med = contribution.median()
        mad = (contribution - med).abs().median()
        threshold = med + self.root_cause_nsigma * max(1.4826 * mad.item(), 0.1)
        
        raw_causes = (contribution > threshold).nonzero(as_tuple=True)[0].tolist()
        
        # 新規: リンク情報があれば上流優先トリアージ
        if links and len(links) > 0 and len(raw_causes) > 1:
            # リンクからグラフを構筑 (出行度の高いノードを上流とみなす)
            out_degree = {i: 0 for i in range(self.num_positions)}
            for i, j, w in links:
                out_degree[i] = out_degree.get(i, 0) + w
            
            # 出行度が高い項目を優先
            sorted_by_out = sorted(raw_causes, key=lambda pos: out_degree.get(pos, 0), reverse=True)
            # 最高出行度の項目を最優先として返す (連鎖下流を除外しやすく)
            return sorted_by_out[:max(1, len(sorted_by_out)//2 + 1)]
        
        return raw_causes

    def build_links_cosine(self, current_step: int) -> List[Tuple[int, int, float]]:
        if current_step < self.window_size or self.num_positions < 2:
            return []
        pos_vectors = self.residue_window.t()
        norms = pos_vectors.norm(dim=1, keepdim=True)
        norms = torch.where(norms == 0, torch.ones_like(norms), norms)
        normalized_vectors = pos_vectors / norms
        cosine_matrix = torch.mm(normalized_vectors, normalized_vectors.t())
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
        x_norm = self._normalize(x)
        new_axis = state.axis * 0.7 + x_norm * 0.3
        new_res = torch.clamp(
            state.residue * self.residue_decay + (x_norm - state.axis),
            -self.residue_cap, self.residue_cap
        )
        new_ten = (new_res - state.residue).abs()
        return new_axis, new_res, new_ten, {}

    def observe_step(self, state: BaseCUBEState, x: torch.Tensor, next_metadata: Optional[CUBEMetadata] = None) -> Tuple[BaseCUBEState, BaseMetrics]:
        new_axis, new_res, new_ten, role_specific = self._compute_core(state, x)
        self.residue_window = torch.cat([self.residue_window[1:], new_res.unsqueeze(0)], dim=0)
        
        res_m = float(new_res.abs().mean())
        ten_m = float(new_ten.mean())
        
        linear_sum = res_m * 2.2 + ten_m * 1.5
        anomaly_score = 1.0 - math.exp(-1.8 * linear_sum)
        
        sustained = self._update_stats_and_threshold_mad(anomaly_score, res_m, ten_m)
        
        is_anomaly = anomaly_score > self.current_threshold
        self.anomaly_duration = self.anomaly_duration + 1 if is_anomaly else 0
        
        new_links = self.build_links_cosine(state.step + 1)
        # リンク情報を原因特定にフィードバック
        root_causes = self._isolate_root_causes(new_res, new_ten, links=new_links) if is_anomaly else []
        
        new_status = self._update_status(state.status, res_m, ten_m)
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


class CUBEHub:
    """ CUBEHub v2.8 """
    
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
            next_state, metrics = cube.observe_step(current_state, x, next_metadata=next_metadata)
            self.states[name] = next_state
            results[name] = metrics
            
            weight = max(0.01, current_state.status["coherence"])
            weighted_score_sum += metrics.anomaly_score * weight
            total_weight += weight
            
            if metrics.is_anomaly:
                all_root_causes.extend(metrics.root_causes)
        
        global_score = weighted_score_sum / total_weight if total_weight > 0 else 0.0
        global_anomaly = global_score > self.global_threshold
        
        num_cubes = len(self.cubes)
        required_votes = (num_cubes // 2) + 1 if num_cubes > 1 else 1
        most_frequent_causes = [c for c in set(all_root_causes) if all_root_causes.count(c) >= required_votes]
        
        self.global_metrics["global_score"] = round(global_score, 4)
        self.global_metrics["global_anomaly"] = global_anomaly
        self.global_metrics["global_root_causes"] = sorted(most_frequent_causes) if global_anomaly else []
        self.global_metrics["last_metadata"] = next_metadata.__dict__ if next_metadata else {}
        
        return results


if __name__ == "__main__":
    import time
    
    print("=== CUBE v2.8 Generalized Demo ===\n")
    
    hub = CUBEHub(global_threshold=0.40)
    
    # normalize_input=True で標準化有効化
    hub.register(SingleRoleCUBE(role_name="NormalizedObserver", num_positions=5, normalize_input=True, norm_method="zscore"))
    hub.register(SingleRoleCUBE(role_name="RawObserver", num_positions=5, normalize_input=False))
    
    for step in range(15):
        normal_input = torch.randn(5) * 0.1
        hub.observe_all(normal_input)
    
    print("--- Normal phase done ---\n")
    
    # スケールが大きい項目と小さい項目が混在する異常
    anomalous_input = torch.tensor([0.1, 0.1, 8.5, 0.1, 0.1])  # ポジション3が大きいスケールの異常
    hub.observe_all(anomalous_input)
    
    print(f"[Anomaly with scale difference]")
    for name, m in hub.observe_all(anomalous_input).items():  # 2回目で確認
        print(f"  {name}: anomaly={m.is_anomaly}, root_causes={m.root_causes}")
