import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run Alembic migrations")
    parser.add_argument("--revision", default="head", help="Target revision (default: head)")
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "alembic", "upgrade", args.revision]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info(f"Migration to {args.revision} successful")
        if result.stdout:
            print(result.stdout)
    else:
        logger.error(f"Migration failed: {result.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
