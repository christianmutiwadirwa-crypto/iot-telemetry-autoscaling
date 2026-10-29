"""
Cluster Telemetry & Auto-Scaling Model (Task L17-L21 / HPA Simulator).

Simulates the behavior of the Kubernetes Horizontal Pod Autoscaler (HPA),
RabbitMQ queue backlog, and TimescaleDB ingestion throughput for the
Metropolitan Seismic Monitoring Command frontend.
Allows realistic visualization of cluster scale-out (2 -> 10 pods) during
seismic spikes and graceful scale-in during post-quake quiescent periods.
"""

import math
from typing import Dict, Any, Optional


class ClusterModel:
    """
    Simulates Kubernetes pod autoscaling, message queuing, and database write rates.
    """

    def __init__(
        self,
        min_pods: int = 2,
        max_pods: int = 10,
        pod_capacity_rps: float = 35.0,
        target_cpu_utilization: float = 0.60,
        scale_in_stabilization_s: float = 15.0,
    ):
        self.min_pods = min_pods
        self.max_pods = max_pods
        self.pod_capacity_rps = pod_capacity_rps
        self.target_cpu_utilization = target_cpu_utilization
        self.scale_in_stabilization_s = scale_in_stabilization_s

        # Dynamic state
        self.replicas: int = min_pods
        self.ready_pods: int = min_pods
        self.starting_pods: int = 0
        self.startup_timer: float = 0.0

        self.queue_depth: float = 0.0
        self.db_writes_per_sec: float = 0.0
        self.cpu_percent: float = 12.0
        self.status: str = "stable"

        self.cooldown_timer: float = 0.0
        self.live_aks_replicas: Optional[int] = None
        self.live_aks_cpu: Optional[float] = None
        self.live_aks_timestamp: float = 0.0
        self.live_ingest: Dict[str, Any] = {"replicas": min_pods, "ready_pods": min_pods, "starting_pods": 0, "cpu_percent": 4.0}
        self.live_processor: Dict[str, Any] = {"replicas": min_pods, "ready_pods": min_pods, "starting_pods": 0, "cpu_percent": 4.0}

    def update_live_cluster(
        self,
        replicas: int,
        ready_pods: Optional[int] = None,
        cpu_percent: Optional[float] = None,
        queue_depth: Optional[int] = None,
        db_writes_per_sec: Optional[int] = None,
        ingest_stats: Optional[Dict[str, Any]] = None,
        processor_stats: Optional[Dict[str, Any]] = None,
    ):
        """Syncs live pod metrics directly from AKS HPA and cluster state."""
        import time
        self.live_aks_replicas = max(self.min_pods, min(self.max_pods, replicas))
        if ready_pods is not None:
            self.live_aks_ready_pods = max(1, min(self.max_pods, ready_pods))
        else:
            self.live_aks_ready_pods = self.live_aks_replicas
        if cpu_percent is not None:
            self.live_aks_cpu = cpu_percent
        if queue_depth is not None:
            self.live_aks_queue = queue_depth
        if db_writes_per_sec is not None:
            self.live_aks_db_writes = db_writes_per_sec
        if ingest_stats is not None:
            self.live_ingest = ingest_stats
        if processor_stats is not None:
            self.live_processor = processor_stats
        self.live_aks_timestamp = time.time()

    def tick(self, current_rps: float, dt: float = 0.1) -> Dict[str, Any]:
        """
        Advance the cluster state by dt seconds given the current incoming requests/second.
        When connected to live Azure AKS, faithfully mirrors the actual cloud state.
        """
        import time
        is_live_aks = self.live_aks_replicas is not None and (time.time() - self.live_aks_timestamp < 15.0)

        # 1. LIVE AKS MODE: Faithfully mirror what Azure is running
        if is_live_aks and self.live_aks_replicas is not None:
            self.replicas = self.live_aks_replicas
            self.ready_pods = getattr(self, "live_aks_ready_pods", self.live_aks_replicas)
            self.starting_pods = max(0, self.replicas - self.ready_pods)
            if self.live_aks_cpu is not None:
                self.cpu_percent = self.live_aks_cpu
            if getattr(self, "live_aks_queue", None) is not None:
                self.queue_depth = float(self.live_aks_queue)
            else:
                # Approximate queue buffering when incoming rps exceeds ready pod capacity
                capacity = self.ready_pods * self.pod_capacity_rps
                if current_rps > capacity:
                    self.queue_depth += (current_rps - capacity) * dt
                else:
                    self.queue_depth = max(0.0, self.queue_depth - (capacity - current_rps) * dt)

            if getattr(self, "live_aks_db_writes", None) is not None:
                self.db_writes_per_sec = float(self.live_aks_db_writes)
            else:
                self.db_writes_per_sec = min(current_rps + (self.queue_depth * 0.2), self.ready_pods * self.pod_capacity_rps)

            if self.starting_pods > 0:
                self.status = "scaling out"
            elif self.replicas > self.min_pods:
                self.status = "scaled"
            else:
                self.status = "stable"

            return {
                "replicas": self.replicas,
                "ready_pods": self.ready_pods,
                "starting_pods": self.starting_pods,
                "min_pods": self.min_pods,
                "max_pods": self.max_pods,
                "queue_depth": int(round(self.queue_depth)),
                "db_writes_per_sec": int(round(self.db_writes_per_sec)),
                "cpu_percent": round(self.cpu_percent, 1),
                "status": self.status,
                "ingest": self.live_ingest,
                "processor": self.live_processor,
            }

        # 2. OFFLINE SIMULATION FALLBACK (when AKS is unreachable)
        effective_load_per_pod = self.pod_capacity_rps * self.target_cpu_utilization
        effective_demand_rps = current_rps + (self.queue_depth * 0.3)
        if effective_demand_rps <= 0.0:
            desired_pods = self.min_pods
        else:
            desired_pods = int(math.ceil(effective_demand_rps / effective_load_per_pod))
            desired_pods = max(self.min_pods, min(self.max_pods, desired_pods))

        if desired_pods > self.replicas:
            added = desired_pods - self.replicas
            self.replicas = desired_pods
            self.starting_pods += added
            self.startup_timer = 1.5
            self.cooldown_timer = self.scale_in_stabilization_s
            self.status = "scaling out"
        elif desired_pods < self.replicas:
            if self.cooldown_timer > 0.0:
                self.cooldown_timer -= dt
                self.status = "cooling down"
            else:
                self.replicas = max(self.min_pods, self.replicas - 1)
                self.ready_pods = min(self.ready_pods, self.replicas)
                self.cooldown_timer = 2.0
                self.status = "scaling in"
        else:
            if self.cooldown_timer > 0.0:
                self.cooldown_timer -= dt
            if self.starting_pods == 0:
                self.status = "scaled" if self.replicas > self.min_pods else "stable"

        # Advance startup of starting pods
        if self.starting_pods > 0:
            self.startup_timer -= dt
            if self.startup_timer <= 0.0:
                self.ready_pods = min(self.replicas, self.ready_pods + self.starting_pods)
                self.starting_pods = 0
                if self.cooldown_timer <= 0.0:
                    self.status = "scaled" if self.replicas > self.min_pods else "stable"

        # Compute cluster capacity and queue backlog
        cluster_capacity = self.ready_pods * self.pod_capacity_rps
        if current_rps > cluster_capacity:
            # Backlog accumulates in RabbitMQ
            excess = current_rps - cluster_capacity
            self.queue_depth += excess * dt
            self.db_writes_per_sec = cluster_capacity
        else:
            # Drain queue backlog
            spare_capacity = cluster_capacity - current_rps
            drain = min(self.queue_depth, spare_capacity * dt)
            self.queue_depth = max(0.0, self.queue_depth - drain)
            self.db_writes_per_sec = current_rps + (drain / dt if dt > 0 else 0.0)

        # CPU utilization calculation
        if self.ready_pods > 0:
            raw_cpu = (current_rps / (self.ready_pods * self.pod_capacity_rps)) * 100.0
            self.cpu_percent = round(max(8.0, min(98.0, raw_cpu)), 1)
        else:
            self.cpu_percent = 99.0

        return {
            "replicas": self.replicas,
            "ready_pods": self.ready_pods,
            "starting_pods": self.starting_pods,
            "min_pods": self.min_pods,
            "max_pods": self.max_pods,
            "queue_depth": int(round(self.queue_depth)),
            "db_writes_per_sec": int(round(self.db_writes_per_sec)),
            "cpu_percent": self.cpu_percent,
            "status": self.status,
            "ingest": {
                "replicas": self.replicas,
                "ready_pods": self.ready_pods,
                "starting_pods": self.starting_pods,
                "cpu_percent": self.cpu_percent,
            },
            "processor": {
                "replicas": self.replicas,
                "ready_pods": self.ready_pods,
                "starting_pods": self.starting_pods,
                "cpu_percent": self.cpu_percent,
            },
        }
