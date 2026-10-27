import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pandas as pd

from src import pitch_logic
from src import pitch_speed_v23_auto_distance as pitch_speed


class FakeCapture:
    def __init__(self, frames):
        self.frames = frames
        self.index = 0

    def isOpened(self):
        return True

    def get(self, property_id):
        return {
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_WIDTH: self.frames[0].shape[1],
            cv2.CAP_PROP_FRAME_HEIGHT: self.frames[0].shape[0],
        }[property_id]

    def read(self):
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index].copy()
        self.index += 1
        return True, frame

    def release(self):
        pass


class FakeWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.frames = []

    def isOpened(self):
        return True

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        self.path.write_bytes(b"encoded test video")


class BallTrajectoryTests(unittest.TestCase):
    def test_draws_multiple_points_at_their_video_frame_numbers(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        tracking = pd.DataFrame(
            [
                {"frame": 0, "cx": 10, "cy": 10},
                {"frame": 1, "cx": 30, "cy": 30},
                {"frame": 2, "cx": 50, "cy": 50},
            ]
        )

        before_second_detection = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=0)
        at_second_detection = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=1)

        np.testing.assert_array_equal(before_second_detection, frame)
        self.assertGreater(int(at_second_detection[20, 20].sum()), 0)

    def test_short_detection_gap_is_bridged_dashed_without_filling_missing_position(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        tracking = pd.DataFrame(
            [{"frame": 0, "cx": 10, "cy": 32}, {"frame": 2, "cx": 50, "cy": 32}]
        )

        rendered = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=2)

        self.assertGreater(int(rendered[32, 14].sum()), 0)
        self.assertEqual(int(rendered[32, 20].sum()), 0)
        self.assertGreater(int(rendered[32, 26].sum()), 0)

    def test_explicitly_interpolated_positions_are_visually_distinct(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        tracking = pd.DataFrame(
            [
                {"frame": 0, "cx": 10, "cy": 32, "is_interpolated": False},
                {"frame": 1, "cx": 50, "cy": 32, "is_interpolated": True},
            ]
        )

        rendered = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=1)

        self.assertGreater(int(rendered[32, 14].sum()), 0)
        self.assertEqual(int(rendered[32, 24].sum()), 0)
        self.assertGreater(int(rendered[32, 50].sum()), 0)

    def test_missing_tracking_data_leaves_frame_unchanged(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        rendered = pitch_logic.draw_ball_trajectory(frame, None, end_frame=10)

        np.testing.assert_array_equal(rendered, frame)

    def test_confidence_less_tracking_csv_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            tracking_path = Path(directory) / "tracking.csv"
            tracking_path.write_text(
                "frame,cx,cy,time_sec\n1,12,24,0.03\n2,16,28,0.06\n",
                encoding="utf-8",
            )

            rows = pitch_speed.load_ball_csv(tracking_path)

        self.assertEqual([row["frame"] for row in rows], [1, 2])

    def test_skeleton_video_uses_supplied_tracking_and_returns_display_path(self):
        frames = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(3)]
        writers = []
        tracking = pd.DataFrame(
            [
                {"frame": 0, "cx": 10, "cy": 10},
                {"frame": 1, "cx": 30, "cy": 30},
                {"frame": 2, "cx": 50, "cy": 50},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos_dir = root / "videos"
            output_dir = root / "output"
            videos_dir.mkdir()
            (videos_dir / "demo.mp4").touch()

            def create_writer(path, *_args):
                writer = FakeWriter(path)
                writers.append(writer)
                return writer

            def encode_video(command, **_kwargs):
                shutil.copyfile(command[command.index("-i") + 1], command[-1])

            with (
                patch.object(pitch_logic, "VIDEOS_DIR", videos_dir),
                patch.object(pitch_logic, "OUTPUT_DIR", output_dir),
                patch.object(pitch_logic.cv2, "VideoCapture", return_value=FakeCapture(frames)),
                patch.object(pitch_logic.cv2, "VideoWriter", side_effect=create_writer),
                patch.object(pitch_logic.subprocess, "run", side_effect=encode_video),
            ):
                output_path = pitch_logic.create_skeleton_video(
                    "demo",
                    pd.DataFrame(columns=["frame"]),
                    force_recreate=True,
                    ball_df=tracking,
                    release_frame=0,
                    net_frame=2,
                )
                self.assertTrue(output_path.exists())
                self.assertEqual(output_path.name, "skeleton_demo.mp4")
                self.assertGreater(int(writers[0].frames[1][20, 20].sum()), 0)

    def test_skeleton_video_without_tracking_does_not_crash(self):
        frames = [np.zeros((64, 64, 3), dtype=np.uint8)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos_dir = root / "videos"
            output_dir = root / "output"
            videos_dir.mkdir()
            (videos_dir / "demo.mp4").touch()
            output_dir.mkdir()

            def encode_video(command, **_kwargs):
                shutil.copyfile(command[command.index("-i") + 1], command[-1])

            with (
                patch.object(pitch_logic, "VIDEOS_DIR", videos_dir),
                patch.object(pitch_logic, "OUTPUT_DIR", output_dir),
                patch.object(pitch_logic.cv2, "VideoCapture", return_value=FakeCapture(frames)),
                patch.object(pitch_logic.cv2, "VideoWriter", side_effect=lambda path, *_args: FakeWriter(path)),
                patch.object(pitch_logic.subprocess, "run", side_effect=encode_video),
            ):
                output_path = pitch_logic.create_skeleton_video(
                    "demo",
                    pd.DataFrame(columns=["frame"]),
                    force_recreate=True,
                    ball_df=None,
                )
                self.assertTrue(output_path.exists())

    def test_draw_uses_frame_numbers_even_when_rows_are_out_of_order(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        tracking = pd.DataFrame(
            [
                {"frame": 2, "cx": 50, "cy": 50},
                {"frame": 0, "cx": 10, "cy": 10},
                {"frame": 1, "cx": 30, "cy": 30},
            ]
        )

        before_detection = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=0)
        after_detection = pitch_logic.draw_ball_trajectory(frame, tracking, end_frame=1)

        np.testing.assert_array_equal(before_detection, frame)
        self.assertGreater(int(after_detection[20, 20].sum()), 0)

    def test_source_and_target_resolution_are_scaled(self):
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        tracking = pd.DataFrame(
            [{"frame": 0, "cx": 10, "cy": 10}, {"frame": 1, "cx": 40, "cy": 30}]
        )

        rendered = pitch_logic.draw_ball_trajectory(
            frame,
            tracking,
            end_frame=1,
            source_size=(50, 50),
            target_size=(200, 100),
        )

        self.assertGreater(int(rendered[60, 160].sum()), 0)
        self.assertEqual(int(rendered[30, 40].sum()), 0)

    def test_valid_output_csv_is_preferred_over_empty_tracking_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            empty_dir = output_dir / "ball_tracking_v5"
            empty_dir.mkdir(parents=True)
            (empty_dir / "demo_tracking.csv").write_text(
                "frame,cx,cy,time_sec\n", encoding="utf-8"
            )
            valid_path = output_dir / "demo_tracking.csv"
            valid_path.write_text(
                "frame,cx,cy,time_sec\n1,12,24,0.03\n2,16,28,0.06\n",
                encoding="utf-8",
            )

            with patch.object(pitch_logic, "OUTPUT_DIR", output_dir):
                tracking, selected_path = pitch_logic.select_ball_tracking_data("demo")

            self.assertIsNotNone(tracking)
            self.assertEqual(selected_path, valid_path)
            self.assertEqual(len(tracking), 2)

    def test_skeleton_video_uses_output_tracking_csv_when_not_supplied(self):
        frames = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(3)]
        writers = []
        tracking = pd.DataFrame(
            [
                {"frame": 0, "cx": 10, "cy": 10},
                {"frame": 1, "cx": 30, "cy": 30},
                {"frame": 2, "cx": 50, "cy": 50},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos_dir = root / "videos"
            output_dir = root / "output"
            videos_dir.mkdir()
            output_dir.mkdir()
            (videos_dir / "demo.mp4").touch()
            tracking.to_csv(output_dir / "demo_tracking.csv", index=False)

            def create_writer(path, *_args):
                writer = FakeWriter(path)
                writers.append(writer)
                return writer

            def encode_video(command, **_kwargs):
                shutil.copyfile(command[command.index("-i") + 1], command[-1])

            with (
                patch.object(pitch_logic, "VIDEOS_DIR", videos_dir),
                patch.object(pitch_logic, "OUTPUT_DIR", output_dir),
                patch.object(pitch_logic.cv2, "VideoCapture", return_value=FakeCapture(frames)),
                patch.object(pitch_logic.cv2, "VideoWriter", side_effect=create_writer),
                patch.object(pitch_logic.subprocess, "run", side_effect=encode_video),
            ):
                output_path = pitch_logic.create_skeleton_video(
                    "demo",
                    pd.DataFrame(columns=["frame"]),
                    force_recreate=True,
                    ball_df=None,
                )

            self.assertEqual(output_path.name, "skeleton_demo.mp4")
            self.assertGreater(int(writers[0].frames[1][20, 20].sum()), 0)

    def test_skeleton_video_cache_is_reused_and_invalidated_by_tracking_change(self):
        frames = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(3)]
        writers = []
        tracking_a = pd.DataFrame(
            [{"frame": 0, "cx": 10, "cy": 10}, {"frame": 1, "cx": 30, "cy": 30}]
        )
        tracking_b = pd.DataFrame(
            [{"frame": 0, "cx": 10, "cy": 10}, {"frame": 1, "cx": 50, "cy": 50}]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos_dir = root / "videos"
            output_dir = root / "output"
            videos_dir.mkdir()
            output_dir.mkdir()
            (videos_dir / "demo.mp4").touch()

            def create_writer(path, *_args):
                writer = FakeWriter(path)
                writers.append(writer)
                return writer

            def encode_video(command, **_kwargs):
                shutil.copyfile(command[command.index("-i") + 1], command[-1])

            with (
                patch.object(pitch_logic, "VIDEOS_DIR", videos_dir),
                patch.object(pitch_logic, "OUTPUT_DIR", output_dir),
                patch.object(pitch_logic.cv2, "VideoCapture", side_effect=lambda *_args, **_kwargs: FakeCapture(frames)),
                patch.object(pitch_logic.cv2, "VideoWriter", side_effect=create_writer),
                patch.object(pitch_logic.subprocess, "run", side_effect=encode_video),
            ):
                pitch_logic.create_skeleton_video(
                    "demo", pd.DataFrame(columns=["frame"]), force_recreate=True, ball_df=tracking_a
                )
                self.assertEqual(len(writers), 1)

                pitch_logic.create_skeleton_video(
                    "demo", pd.DataFrame(columns=["frame"]), ball_df=tracking_a
                )
                self.assertEqual(len(writers), 1)

                pitch_logic.create_skeleton_video(
                    "demo", pd.DataFrame(columns=["frame"]), ball_df=tracking_b
                )
                self.assertEqual(len(writers), 2)
                self.assertGreater(int(writers[1].frames[1][40, 40].sum()), 0)

    def test_measured_tracking_is_preferred_over_synthetic_output_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            measured_dir = output_dir / "ball_tracking_v5"
            measured_dir.mkdir(parents=True)
            measured_path = measured_dir / "demo_tracking.csv"
            measured_path.write_text(
                "frame,time_sec,cx,cy,confidence,interpolated\n"
                "10,0.33,100,200,0.9,0\n"
                "11,0.37,110,205,0.8,0\n",
                encoding="utf-8",
            )
            (output_dir / "demo_tracking.csv").write_text(
                "frame,cx,cy,time_sec\n10,500,500,0.33\n11,510,505,0.37\n",
                encoding="utf-8",
            )

            with patch.object(pitch_logic, "OUTPUT_DIR", output_dir):
                tracking, selected_path = pitch_logic.select_ball_tracking_data(
                    "demo", release_frame=10, net_frame=20
                )

            self.assertEqual(selected_path, measured_path)
            self.assertEqual(float(tracking.iloc[0]["cx"]), 100.0)

    def test_tracking_outside_release_window_is_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            output_dir.mkdir(parents=True)
            (output_dir / "demo_tracking.csv").write_text(
                "frame,cx,cy,time_sec\n1,12,24,0.03\n2,16,28,0.06\n",
                encoding="utf-8",
            )

            with patch.object(pitch_logic, "OUTPUT_DIR", output_dir):
                tracking, selected_path = pitch_logic.select_ball_tracking_data(
                    "demo", release_frame=100, net_frame=120
                )

            self.assertIsNone(tracking)
            self.assertIsNone(selected_path)

    def test_slow_video_helper_forwards_tracking_data(self):
        tracking = pd.DataFrame(
            [{"frame": 0, "cx": 10, "cy": 10}, {"frame": 1, "cx": 30, "cy": 30}]
        )
        expected = Path("skeleton_demo.mp4")

        with patch.object(pitch_logic, "create_skeleton_video", return_value=expected) as create:
            result = pitch_logic.get_or_create_slow_video(
                "demo",
                pd.DataFrame(columns=["frame"]),
                speed_factor=1.0,
                ball_df=tracking,
                release_frame=0,
                net_frame=1,
            )

        self.assertEqual(result, expected)
        kwargs = create.call_args.kwargs
        self.assertIs(kwargs["ball_df"], tracking)
        self.assertEqual(kwargs["release_frame"], 0)
        self.assertEqual(kwargs["net_frame"], 1)

    def test_app_display_call_forwards_tracking_data(self):
        app_source = Path(pitch_logic.__file__).with_name("app.py").read_text(encoding="utf-8")
        call_start = app_source.index("active_video_path = pitch_logic.get_or_create_slow_video(")
        call_block = app_source[call_start:call_start + 500]

        self.assertIn("ball_df=ball_df", call_block)
        self.assertIn("release_frame=release_frame", call_block)
        self.assertIn("net_frame=net_frame", call_block)


if __name__ == "__main__":
    unittest.main()
