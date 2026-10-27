import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src import aws_utils


class TestAwsUtilsS3Upload(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_upload_returns_false_when_no_bucket_configured(self):
        os.environ.pop("AWS_S3_BUCKET_NAME", None)
        self.assertFalse(aws_utils.is_aws_configured())
        result = aws_utils.upload_file_to_s3("dummy_path.mp4", "videos/dummy_path.mp4")
        self.assertFalse(result)

    def test_upload_returns_false_when_bucket_name_is_empty(self):
        os.environ["AWS_S3_BUCKET_NAME"] = "   "
        result = aws_utils.upload_file_to_s3("dummy_path.mp4", "videos/dummy_path.mp4")
        self.assertFalse(result)

    @patch("src.aws_utils.get_s3_client")
    def test_upload_success(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        local_path = "videos/sample.mp4"
        s3_key = "videos/sample.mp4"
        result = aws_utils.upload_file_to_s3(local_path, s3_key)

        self.assertTrue(result)
        mock_s3.upload_file.assert_called_once_with(str(local_path), "test-bucket", s3_key)

    @patch("src.aws_utils.get_s3_client")
    def test_upload_returns_false_on_client_error(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject"
        )
        mock_get_client.return_value = mock_s3

        result = aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertFalse(result)

    @patch("src.aws_utils.get_s3_client")
    def test_upload_returns_false_on_unexpected_exception(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = RuntimeError("Network timeout")
        mock_get_client.return_value = mock_s3

        result = aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertFalse(result)


class TestAwsUtilsBedrockResolver(unittest.TestCase):
    def test_resolve_bedrock_model_id_regional_profiles(self):
        self.assertEqual(
            aws_utils.resolve_bedrock_model_id("ap-northeast-1"),
            "jp.amazon.nova-2-lite-v1:0"
        )
        self.assertEqual(
            aws_utils.resolve_bedrock_model_id("us-east-1"),
            "us.amazon.nova-2-lite-v1:0"
        )
        self.assertEqual(
            aws_utils.resolve_bedrock_model_id("eu-central-1"),
            "eu.amazon.nova-2-lite-v1:0"
        )
        self.assertEqual(
            aws_utils.resolve_bedrock_model_id("ap-southeast-2"),
            "global.amazon.nova-2-lite-v1:0"
        )


if __name__ == "__main__":
    unittest.main()
