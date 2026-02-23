"""
Test data loading from S3/DVC for compliance-friendly test execution.

Test data is stored in S3 with DVC pointers in Git. This module handles
fetching data at runtime, caching, and providing fixtures for tests.
"""
import os
import json
from pathlib import Path
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError


class TestDataLoader:
    """
    Loads test data from S3 or local cache.

    Supports:
    - Direct S3 loading for Kubernetes execution
    - Local file loading for development
    - DVC-managed data versioning
    """

    def __init__(
        self,
        s3_bucket: str | None = None,
        s3_prefix: str = "test-data",
        local_data_path: Path | None = None,
    ):
        """
        Initialize data loader.

        Args:
            s3_bucket: S3 bucket name (from env var TEST_DATA_BUCKET if not provided)
            s3_prefix: Prefix/folder in S3 bucket
            local_data_path: Path to local data directory for development
        """
        self.s3_bucket = s3_bucket or os.environ.get("TEST_DATA_BUCKET")
        self.s3_prefix = s3_prefix
        self.local_data_path = local_data_path or Path("data")
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def _load_from_s3(self, key: str) -> dict[str, Any]:
        """Load JSON data from S3."""
        if not self.s3_bucket:
            raise ValueError(
                "S3 bucket not configured. Set TEST_DATA_BUCKET environment variable."
            )

        full_key = f"{self.s3_prefix}/{key}"

        try:
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=full_key,
            )
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            raise RuntimeError(
                f"Failed to load test data from S3: s3://{self.s3_bucket}/{full_key}"
            ) from e

    def _load_from_local(self, filename: str) -> dict[str, Any]:
        """Load JSON data from local file."""
        file_path = self.local_data_path / filename

        if not file_path.exists():
            raise FileNotFoundError(
                f"Test data file not found: {file_path}. "
                f"Run 'dvc pull' to fetch test data."
            )

        with open(file_path, "r") as f:
            return json.load(f)

    @lru_cache(maxsize=50)
    def load_test_cases(self, dataset_name: str) -> list[dict[str, Any]]:
        """
        Load test cases from a dataset.

        Args:
            dataset_name: Name of dataset file (without .json extension)

        Returns:
            List of test case dictionaries
        """
        filename = f"{dataset_name}.json"

        # Try S3 first (for Kubernetes), fall back to local
        if self.s3_bucket and os.environ.get("KUBERNETES_SERVICE_HOST"):
            data = self._load_from_s3(filename)
        else:
            data = self._load_from_local(filename)

        return data.get("test_cases", [])

    def load_expected_output(
        self,
        test_id: str,
        dataset_name: str = "expected_outputs",
    ) -> dict[str, Any]:
        """
        Load expected output for a specific test.

        Args:
            test_id: Unique identifier for the test case
            dataset_name: Name of expected outputs dataset

        Returns:
            Expected output dictionary
        """
        all_expectations = self.load_test_cases(dataset_name)

        for expectation in all_expectations:
            if expectation.get("id") == test_id:
                return expectation

        raise KeyError(f"No expected output found for test_id: {test_id}")

    def get_golden_dataset(self, category: str) -> list[dict[str, Any]]:
        """
        Load a golden dataset for a specific category.

        Golden datasets contain verified input/output pairs for regression testing.

        Args:
            category: Category name (e.g., "weather", "search", "conversation")

        Returns:
            List of golden test cases
        """
        return self.load_test_cases(f"golden/{category}")


# Singleton instance for convenience
_default_loader: TestDataLoader | None = None


def get_data_loader() -> TestDataLoader:
    """Get or create the default data loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = TestDataLoader()
    return _default_loader
