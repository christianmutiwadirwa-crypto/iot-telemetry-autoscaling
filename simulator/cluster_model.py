"""
Cluster Telemetry & Auto-Scaling Model (Task L17-L21 / HPA Simulator).

Simulates the behavior of the Kubernetes Horizontal Pod Autoscaler (HPA),
RabbitMQ queue backlog, and TimescaleDB ingestion throughput for the
Metropolitan Seismic Monitoring Command frontend.
Allows realistic visualization of cluster scale-out (2 -> 10 pods) during
seismic spikes and graceful scale-in during post-quake quiescent periods.
"""

import math
from typing import Dict, Any


class ClusterModel:
    """
    Simulates Kubernetes pod autoscaling, message queuing, and database write rates.
    """

    def __init__(
        self,
        min_pods: int = 2,
        max_pods: int = 10,
        pod_capacity_rps: float = 450.0,
        target_cpu_utilization: float = 0.60,
        scale_in_stabilization_s: float = 60.0,
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

    def tick(self, current_rps: float, dt: float = 0.1) -> Dict[str, Any]:
        """
        Advance the cluster state by dt seconds given the current incoming requests/second.
        """
        # Calculate target pods required to maintain 60% CPU target
        effective_load_per_pod = self.pod_capacity_rps * self.target_cpu_utilization
        if current_rps <= 0.0:
            desired_pods = self.min_pods
        else:
            desired_pods = int(math.ceil(current_rps / effective_load_per_pod))
            desired_pods = max(self.min_pods, min(self.max_pods, desired_pods))

        # Check scaling action
        if desired_pods > self.replicas:
            # Scale-out triggered immediately (fast reaction)
            added = desired_pods - self.replicas
            self.replicas = desired_pods
            self.starting_pods += added
            self.startup_timer = 5.0  # pods take 5s to boot
            self.cooldown_timer = self.scale_in_stabilization_s
            self.status = "scaling out"
        elif desired_pods < self.replicas:
            # Pod scale-down requires stabilization cooldown
            if self.cooldown_timer > 0.0:
                self.cooldown_timer -= dt
                self.status = "cooling down"
            else:
                # Scale down gradually (1 pod at a time every 4s)
                self.replicas = max(self.min_pods, self.replicas - 1)
                self.ready_pods = min(self.ready_pods, self.replicas)
                self.cooldown_timer = 4.0
                self.status = "scaling in"
        else:
            if self.cooldown_timer > 0.0:
                self.cooldown_timer -= dt
            if self.starting_pods == 0:
                self.status = "stable"

        # Advance startup of starting pods
        if self.starting_pods > 0:
            self.startup_timer -= dt
            if self.startup_timer <= 0.0:
                self.ready_pods = min(self.replicas, self.ready_pods + self.starting_pods)
                self.starting_pods = 0
                if self.cooldown_timer <= 0.0:
                    self.status = "stable"

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
        }
