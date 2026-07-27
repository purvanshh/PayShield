import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Rollback Alembic migrations")
    parser.add_argument("--revision", default="-1", help="Number of revisions to rollback (default: -1)")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.confirm:
        response = input(f"Rollback migration by {args.revision} revision(s)? [y/N]: ")
        if response.lower() != "y":
            print("Cancelled.")
            return

    cmd = [sys.executable, "-m", "alembic", "downgrade", args.revision]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info(f"Rollback by {args.revision} successful")
        if result.stdout:
            print(result.stdout)
    else:
        logger.error(f"Rollback failed: {result.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
