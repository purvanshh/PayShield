import structlog


class TestLoggingConfig:
    def test_configure_logging_imports(self):
        from observability.logging_config import configure_logging
        configure_logging()
        logger = structlog.get_logger()
        assert logger is not None

    def test_logger_emits_json(self, capsys):
        from observability.logging_config import configure_logging
        configure_logging()
        logger = structlog.get_logger()
        logger.info("test_message", component="test")
        captured = capsys.readouterr()
        assert "test_message" in captured.out

    def test_logger_context(self):
        logger = structlog.get_logger()
        bound = logger.bind(trace_id="abc123")
        assert bound is not None
