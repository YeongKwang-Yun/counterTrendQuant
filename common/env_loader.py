from dotenv import load_dotenv
from pathlib import Path


def load_project_env():
    current_dir = Path(__file__).resolve().parent
    for path in [current_dir, *current_dir.parents]:
        env_path = path / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return env_path
    raise FileNotFoundError(".env file not found")