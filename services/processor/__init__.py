"""
Seismic Telemetry Processor Microservice
Consumes RabbitMQ queues, computes FFT/RMS, correlates events, and stores to TimescaleDB.
"""

__version__ = "0.1.0"
