"""RecoverAI intelligence layer — deterministic, explainable, versioned.

This package is independent of FastAPI: pure functions over dataclasses, with
all database access performed by callers (services/repositories). The same
payment + the same historical database state ALWAYS produce the same decision.
"""

from app.intelligence.engine import RecoveryIntelligenceEngine, build_feature_context
from app.intelligence.features import FeatureExtractor, RecoveryFeatures

__all__ = ["RecoveryIntelligenceEngine", "build_feature_context", "FeatureExtractor", "RecoveryFeatures"]
