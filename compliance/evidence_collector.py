import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


EVIDENCE_SOURCES = {
    "database_schema": "alembic/versions/",
    "configuration": "configs/",
    "model_registry": "models/registry/",
    "dr_docs": "dr/",
    "sre_docs": "sre/",
    "k8s_manifests": "k8s/",
    "compliance_reports": "compliance/reports/",
}


class EvidenceArchive:
    def __init__(self, archive_path: str):
        self.archive_path = archive_path
        self.manifest: dict[str, str] = {}

    def add_file(self, rel_path: str, content: str):
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        self.manifest[rel_path] = file_hash

    def generate_manifest(self) -> dict[str, str]:
        return self.manifest

    def verify_integrity(self) -> bool:
        if not os.path.exists(self.archive_path):
            return False
        try:
            with tarfile.open(self.archive_path, "r:gz") as tar:
                manifest_member = tar.extractfile("manifest.json")
                if not manifest_member:
                    return False
                stored_manifest = json.loads(manifest_member.read())
                for path, expected_hash in stored_manifest.items():
                    if path == "manifest.json":
                        continue
                    member = tar.extractfile(path)
                    if not member:
                        return False
                    actual_hash = hashlib.sha256(member.read()).hexdigest()
                    if actual_hash != expected_hash:
                        logger.warning(f"Integrity violation: {path} hash mismatch")
                        return False
            return True
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            return False


class EvidenceCollector:
    def __init__(self, output_dir: str = "compliance/evidence"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def collect_evidence(self, sources: dict[str, str] | None = None) -> str:
        sources = sources or EVIDENCE_SOURCES
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"evidence_{timestamp}.tar.gz"
        archive_path = os.path.join(self.output_dir, archive_name)

        archive = EvidenceArchive(archive_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = os.path.join(tmpdir, "evidence")
            os.makedirs(evidence_dir)

            for name, source_path in sources.items():
                if os.path.exists(source_path):
                    dest = os.path.join(evidence_dir, name)
                    if os.path.isfile(source_path):
                        shutil.copy2(source_path, dest)
                    elif os.path.isdir(source_path):
                        shutil.copytree(source_path, dest, dirs_exist_ok=True)

            manifest = {}
            for root, dirs, files in os.walk(evidence_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, evidence_dir)
                    with open(fpath, "rb") as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                    manifest[rel_path] = file_hash

            manifest_path = os.path.join(evidence_dir, "manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(evidence_dir, arcname="")

        file_size = os.path.getsize(archive_path)
        logger.info(f"Evidence archive created: {archive_path} ({file_size / 1024:.1f} KB)")
        return archive_path

    def verify_archive(self, archive_path: str) -> bool:
        archive = EvidenceArchive(archive_path)
        result = archive.verify_integrity()
        if result:
            logger.info(f"Archive integrity verified: {archive_path}")
        else:
            logger.error(f"Archive integrity FAILED: {archive_path}")
        return result

    def list_archives(self) -> list[dict[str, Any]]:
        archives = []
        if os.path.isdir(self.output_dir):
            for fname in sorted(os.listdir(self.output_dir)):
                if fname.endswith(".tar.gz"):
                    fpath = os.path.join(self.output_dir, fname)
                    fsize = os.path.getsize(fpath)
                    archives.append({
                        "name": fname,
                        "size_kb": round(fsize / 1024, 1),
                        "created": datetime.fromtimestamp(
                            os.path.getctime(fpath)
                        ).isoformat(),
                    })
        return archives
