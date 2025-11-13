"""
Integrity Baseline Generator - Creates and verifies file integrity baselines

This module creates a "snapshot" of workflow files during validation that can be used
for future integrity verification. It stores checksums, sizes, and metadata for all
workflow data files.
"""
import json
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class IntegrityBaseline:
    """
    Creates and manages integrity baselines for workflow files

    A baseline includes:
    - File checksums (MD5, SHA256)
    - File sizes
    - File timestamps
    - File metadata
    - Workflow version
    """

    def __init__(self, baseline_path: Optional[str] = None):
        """
        Initialize baseline manager

        Args:
            baseline_path: Path to baseline file (default: .workflow_integrity.json)
        """
        self.baseline_path = baseline_path or '.workflow_integrity.json'

    def generate_baseline(self, workflow_path: str, replica_catalog: Dict[str, Any],
                         transformation_catalog: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate integrity baseline for workflow files

        Args:
            workflow_path: Path to workflow YAML
            replica_catalog: Replica catalog dict
            transformation_catalog: Transformation catalog dict

        Returns:
            Baseline dictionary
        """
        baseline = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'workflow': workflow_path,
            'files': {},
            'executables': {},
            'statistics': {
                'total_files': 0,
                'total_size_bytes': 0,
                'total_executables': 0
            }
        }

        # Process replica catalog files
        replicas = self._extract_replicas(replica_catalog)
        for replica in replicas:
            lfn = replica.get('lfn')
            pfns = self._extract_pfns(replica)

            for pfn in pfns:
                if os.path.exists(pfn):
                    try:
                        file_info = self._compute_file_info(pfn, lfn)
                        baseline['files'][lfn] = file_info
                        baseline['statistics']['total_files'] += 1
                        baseline['statistics']['total_size_bytes'] += file_info['size_bytes']
                        logger.info(f"✓ Baseline created for: {lfn}")
                    except Exception as e:
                        logger.warning(f"Could not create baseline for {lfn}: {e}")

        # Process transformation catalog executables
        transformations = self._extract_transformations(transformation_catalog)
        for trans in transformations:
            name = trans.get('name')
            pfn = trans.get('pfn')

            if pfn and os.path.exists(pfn):
                try:
                    exec_info = self._compute_file_info(pfn, name)
                    exec_info['is_executable'] = os.access(pfn, os.X_OK)
                    baseline['executables'][name] = exec_info
                    baseline['statistics']['total_executables'] += 1
                    logger.info(f"✓ Baseline created for executable: {name}")
                except Exception as e:
                    logger.warning(f"Could not create baseline for {name}: {e}")

        return baseline

    def save_baseline(self, baseline: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        Save baseline to JSON file

        Args:
            baseline: Baseline dictionary
            output_path: Output file path (default: self.baseline_path)

        Returns:
            Path to saved baseline file
        """
        path = output_path or self.baseline_path

        with open(path, 'w') as f:
            json.dump(baseline, f, indent=2)

        logger.info(f"💾 Integrity baseline saved to: {path}")
        return path

    def load_baseline(self, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load baseline from JSON file

        Args:
            path: Path to baseline file (default: self.baseline_path)

        Returns:
            Baseline dictionary or None if not found
        """
        path = path or self.baseline_path

        if not os.path.exists(path):
            logger.info(f"No baseline found at: {path}")
            return None

        try:
            with open(path, 'r') as f:
                baseline = json.load(f)
            logger.info(f"📂 Loaded baseline from: {path} (created: {baseline.get('created_at')})")
            return baseline
        except Exception as e:
            logger.error(f"Failed to load baseline: {e}")
            return None

    def verify_against_baseline(self, baseline: Dict[str, Any], replica_catalog: Dict[str, Any],
                                transformation_catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Verify current files against baseline

        Args:
            baseline: Baseline dictionary
            replica_catalog: Current replica catalog
            transformation_catalog: Current transformation catalog

        Returns:
            List of integrity issues found
        """
        issues = []

        # Verify replica files
        replicas = self._extract_replicas(replica_catalog)
        for replica in replicas:
            lfn = replica.get('lfn')
            pfns = self._extract_pfns(replica)

            if lfn not in baseline['files']:
                issues.append({
                    'type': 'new_file',
                    'severity': 'info',
                    'lfn': lfn,
                    'message': f"New file not in baseline: {lfn}"
                })
                continue

            baseline_info = baseline['files'][lfn]

            for pfn in pfns:
                if not os.path.exists(pfn):
                    issues.append({
                        'type': 'missing_file',
                        'severity': 'error',
                        'lfn': lfn,
                        'pfn': pfn,
                        'message': f"File missing (was in baseline): {pfn}"
                    })
                    continue

                # Verify file integrity
                try:
                    current_info = self._compute_file_info(pfn, lfn)

                    # Check size
                    if current_info['size_bytes'] != baseline_info['size_bytes']:
                        issues.append({
                            'type': 'size_mismatch',
                            'severity': 'error',
                            'lfn': lfn,
                            'pfn': pfn,
                            'expected': baseline_info['size_bytes'],
                            'actual': current_info['size_bytes'],
                            'message': f"File size changed: {lfn} (expected: {baseline_info['size_bytes']} bytes, got: {current_info['size_bytes']} bytes)"
                        })

                    # Check MD5
                    if current_info['md5'] != baseline_info['md5']:
                        issues.append({
                            'type': 'checksum_mismatch',
                            'severity': 'critical',
                            'lfn': lfn,
                            'pfn': pfn,
                            'expected_md5': baseline_info['md5'],
                            'actual_md5': current_info['md5'],
                            'message': f"File content changed (checksum mismatch): {lfn}"
                        })

                    # Check SHA256
                    if current_info['sha256'] != baseline_info['sha256']:
                        issues.append({
                            'type': 'checksum_mismatch',
                            'severity': 'critical',
                            'lfn': lfn,
                            'pfn': pfn,
                            'expected_sha256': baseline_info['sha256'],
                            'actual_sha256': current_info['sha256'],
                            'message': f"File content changed (SHA256 mismatch): {lfn}"
                        })

                    # Check modification time (warning only)
                    if current_info['modified_at'] != baseline_info['modified_at']:
                        issues.append({
                            'type': 'timestamp_changed',
                            'severity': 'warning',
                            'lfn': lfn,
                            'pfn': pfn,
                            'message': f"File modification time changed: {lfn}"
                        })

                except Exception as e:
                    issues.append({
                        'type': 'verification_error',
                        'severity': 'error',
                        'lfn': lfn,
                        'pfn': pfn,
                        'message': f"Could not verify file: {e}"
                    })

        # Check for files in baseline that are no longer in catalog
        current_lfns = {r.get('lfn') for r in replicas}
        for lfn in baseline['files'].keys():
            if lfn not in current_lfns:
                issues.append({
                    'type': 'removed_from_catalog',
                    'severity': 'warning',
                    'lfn': lfn,
                    'message': f"File in baseline but removed from replica catalog: {lfn}"
                })

        return issues

    def _extract_replicas(self, replica_catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract replicas from catalog (handles multiple formats)"""
        if not replica_catalog:
            return []

        # Pegasus 5.0+ format
        if 'replicaCatalog' in replica_catalog and 'replicas' in replica_catalog['replicaCatalog']:
            return replica_catalog['replicaCatalog']['replicas']
        # Older format
        elif 'replicas' in replica_catalog:
            return replica_catalog['replicas']

        return []

    def _extract_pfns(self, replica: Dict[str, Any]) -> List[str]:
        """Extract PFNs from replica entry (handles multiple formats)"""
        pfns = []

        # Old format: single 'pfn' field
        if 'pfn' in replica:
            pfns.append(replica['pfn'])

        # Pegasus 5.0+: 'pfns' array
        elif 'pfns' in replica:
            for pfn_entry in replica['pfns']:
                if isinstance(pfn_entry, dict) and 'pfn' in pfn_entry:
                    pfns.append(pfn_entry['pfn'])
                elif isinstance(pfn_entry, str):
                    pfns.append(pfn_entry)

        return pfns

    def _extract_transformations(self, transformation_catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract transformations from catalog (handles multiple formats)"""
        if not transformation_catalog:
            return []

        # Pegasus 5.0+ format
        if 'transformationCatalog' in transformation_catalog and 'transformations' in transformation_catalog['transformationCatalog']:
            return transformation_catalog['transformationCatalog']['transformations']
        # Older format
        elif 'transformations' in transformation_catalog:
            return transformation_catalog['transformations']

        return []

    def _compute_file_info(self, file_path: str, logical_name: str) -> Dict[str, Any]:
        """
        Compute comprehensive file information

        Args:
            file_path: Physical file path
            logical_name: Logical file name

        Returns:
            Dictionary with file information
        """
        stat = os.stat(file_path)

        # Compute checksums
        md5_hash = hashlib.md5()
        sha256_hash = hashlib.sha256()

        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b''):
                md5_hash.update(chunk)
                sha256_hash.update(chunk)

        return {
            'lfn': logical_name,
            'pfn': file_path,
            'size_bytes': stat.st_size,
            'size_human': self._human_readable_size(stat.st_size),
            'md5': md5_hash.hexdigest(),
            'sha256': sha256_hash.hexdigest(),
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'permissions': oct(stat.st_mode)[-3:],
            'is_readable': os.access(file_path, os.R_OK)
        }

    def _human_readable_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
