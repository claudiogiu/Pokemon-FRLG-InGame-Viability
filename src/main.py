import logging

from src.pipeline.orchestrator import StudyOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

if __name__ == "__main__":
    StudyOrchestrator().run()
