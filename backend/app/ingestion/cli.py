from app.config import get_settings
from app.ingestion.pipeline import IngestionPipeline


if __name__ == "__main__":
    print(IngestionPipeline(get_settings()).run())