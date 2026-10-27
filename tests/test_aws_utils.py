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
    def test_upload_failure_remembers_bucket_not_configured(self):
        os.environ.pop("AWS_S3_BUCKET_NAME", None)
        aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertEqual(aws_utils.get_last_s3_error(), "bucket not configured")

    @patch("src.aws_utils.get_s3_client")
    def test_upload_failure_remembers_client_error_code(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject"
        )
        mock_get_client.return_value = mock_s3

        aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertEqual(aws_utils.get_last_s3_error(), "AccessDenied")

    @patch("src.aws_utils.get_s3_client")
    def test_upload_failure_remembers_no_credentials_error(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_get_client.return_value = None

        aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertEqual(aws_utils.get_last_s3_error(), "NoCredentialsError")

    @patch("src.aws_utils.get_s3_client")
    def test_upload_success_clears_last_s3_error(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        aws_utils.upload_file_to_s3("videos/sample.mp4", "videos/sample.mp4")
        self.assertIsNone(aws_utils.get_last_s3_error())



class TestAwsUtilsS3ListAndDownload(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.copy()
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    @patch("src.aws_utils.get_s3_client")
    def test_list_videos_in_s3_filters_and_sorts_newest_first(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "videos/older_pitch.mp4",
                    "Size": 1024,
                    "LastModified": "2026-01-01T10:00:00Z",
                },
                {
                    "Key": "videos/notes.txt",
                    "Size": 200,
                    "LastModified": "2026-02-01T10:00:00Z",
                },
                {
                    "Key": "videos/newest_pitch.MOV",
                    "Size": 2048,
                    "LastModified": "2026-03-01T10:00:00Z",
                },
                {
                    "Key": "videos/",
                    "Size": 0,
                    "LastModified": "2026-03-01T10:00:00Z",
                },
            ]
        }

        videos = aws_utils.list_videos_in_s3()
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0]["name"], "newest_pitch.MOV")
        self.assertEqual(videos[0]["key"], "videos/newest_pitch.MOV")
        self.assertEqual(videos[0]["size_bytes"], 2048)
        self.assertEqual(videos[1]["name"], "older_pitch.mp4")

    def test_list_videos_returns_empty_when_unconfigured(self):
        os.environ.pop("AWS_S3_BUCKET_NAME", None)
        self.assertEqual(aws_utils.list_videos_in_s3(), [])

    @patch("src.aws_utils.get_s3_client")
    def test_download_video_rejects_path_traversal(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            res1 = aws_utils.download_video_from_s3("videos/../../etc/passwd", dest_dir=tmpdir)
            self.assertIsNone(res1)

            res2 = aws_utils.download_video_from_s3("videos/../other.mp4", dest_dir=tmpdir)
            self.assertIsNone(res2)

            res3 = aws_utils.download_video_from_s3("not_videos/hack.mp4", dest_dir=tmpdir)
            self.assertIsNone(res3)

        mock_s3.download_file.assert_not_called()

    @patch("src.aws_utils.get_s3_client")
    def test_download_video_rejects_size_over_100mb(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 101 * 1024 * 1024}

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            res = aws_utils.download_video_from_s3("videos/huge.mp4", dest_dir=tmpdir)
            self.assertIsNone(res)

        mock_s3.download_file.assert_not_called()

    @patch("src.aws_utils.get_s3_client")
    def test_download_video_skips_when_identical_local_file_exists(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "existing.mp4"
            local_file.write_bytes(b"x" * 500)
            mock_s3.head_object.return_value = {"ContentLength": 500}

            res = aws_utils.download_video_from_s3("videos/existing.mp4", dest_dir=tmpdir)
            self.assertEqual(res, local_file)
            mock_s3.download_file.assert_not_called()

    @patch("src.aws_utils.get_s3_client")
    def test_download_video_downloads_when_needed(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 1000}

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            res = aws_utils.download_video_from_s3("videos/pitch_102_1.mp4", dest_dir=tmpdir)
            expected_dest = Path(tmpdir) / "pitch_102_1.mp4"
            self.assertEqual(res, expected_dest)
            mock_s3.download_file.assert_called_once_with(
                "test-bucket", "videos/pitch_102_1.mp4", str(expected_dest)
            )

class TestAwsUtilsResultSummary(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.copy()
        os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    @patch("src.aws_utils.get_s3_client")
    def test_save_result_summary_success(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        summary = {
            "video": "pitch_102_1",
            "fps": 30.0,
            "release_frame": 51,
            "arrival_frame": 70,
            "frame_source": "preset",
            "flight_time_s": 0.6343,
            "extension_m": 1.14,
            "pitch_distance_m": 17.30,
            "velocity_kmh": 102.73,
            "spin_rate_rpm": 1650,
        }

        ok = aws_utils.save_result_summary_to_s3("pitch_102_1", summary)
        self.assertTrue(ok)
        mock_s3.put_object.assert_called_once()
        kwargs = mock_s3.put_object.call_args[1]
        self.assertEqual(kwargs["Bucket"], "test-bucket")
        self.assertEqual(kwargs["Key"], "results/pitch_102_1.json")
        self.assertEqual(kwargs["ContentType"], "application/json")

        import json
        payload = json.loads(kwargs["Body"].decode("utf-8"))
        self.assertEqual(payload["video"], "pitch_102_1")
        self.assertEqual(payload["release_frame"], 51)
        self.assertEqual(payload["arrival_frame"], 70)
        self.assertEqual(payload["frame_source"], "preset")
        self.assertEqual(payload["velocity_kmh"], 102.73)
        self.assertIn("timestamp", payload)
        self.assertIn("git_commit", payload)

    @patch("src.aws_utils.get_s3_client")
    def test_save_result_summary_failure_on_client_error(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject"
        )
        mock_get_client.return_value = mock_s3

        ok = aws_utils.save_result_summary_to_s3("pitch_102_1", {"velocity_kmh": 100.0})
        self.assertFalse(ok)


class TestAwsUtilsStatus(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    @patch("src.aws_utils.get_s3_client")
    def test_get_aws_status_reachable(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "my-test-bucket"
        os.environ["AWS_REGION"] = "us-east-1"
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_get_client.return_value = mock_s3

        status = aws_utils.get_aws_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["bucket"], "my-test-bucket")
        self.assertEqual(status["region"], "us-east-1")
        self.assertTrue(status["s3_reachable"])
        self.assertIsNone(status["s3_error"])

        import json
        status_str = json.dumps(status)
        for sensitive in ("AKIA", "ASIA", "SECRET", "TOKEN", "PASSWORD"):
            self.assertNotIn(sensitive, status_str.upper())

    @patch("src.aws_utils.get_s3_client")
    def test_get_aws_status_unreachable_on_error(self, mock_get_client):
        os.environ["AWS_S3_BUCKET_NAME"] = "my-test-bucket"
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket"
        )
        mock_get_client.return_value = mock_s3

        status = aws_utils.get_aws_status()
        self.assertTrue(status["configured"])
        self.assertFalse(status["s3_reachable"])
        self.assertIn("404", status["s3_error"])



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
