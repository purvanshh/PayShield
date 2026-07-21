class FeatureStore:
    def __init__(self, redis_client):
        self.redis = redis_client

    def increment_velocity_counter(self, user_id: str, timestamp: float):
        pass

    def get_velocity_stats(self, user_id: str):
        pass

    def set_user_baseline(self, user_id: str, baseline: dict):
        pass

    def get_user_baseline(self, user_id: str) -> dict | None:
        pass
