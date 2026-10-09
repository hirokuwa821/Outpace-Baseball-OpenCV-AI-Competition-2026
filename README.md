# Outpace Baseball

**Outpace Baseball** is a video-based baseball pitching analysis project submitted to the **OpenCV AI Competition 2026**, powered by AWS. It combines pose estimation, video processing, and pitch-analysis visualizations in a Streamlit application.

## 1. Project Overview

The application analyzes a locally available pitching video and presents estimated pitch and pitching-mechanics indicators. It is intended as an exploratory coaching and visualization tool; its outputs depend on the video, available tracking data, and the assumptions described below.

The project includes a Streamlit interface, a YOLO pose model, video-analysis modules, and an optional Amazon S3 upload integration. The source code does not establish that the application is publicly deployed.

## 2. Problem and Motivation

Pitching video can be useful for reviewing mechanics, but extracting consistent measurements and comparing pitches manually takes time. Outpace Baseball aims to make selected video-derived measurements easier to inspect by combining pose keypoints, frame timing, calculated estimates, and visual summaries in one application.

The project is a prototype. Its calculated values should not be treated as calibrated measurements or as a replacement for dedicated tracking equipment or professional coaching.

## 3. Key Features

### Implemented in the project

- A Streamlit interface for selecting local videos and uploading MP4 or MOV clips.
- YOLO11 pose inference for extracting pitcher keypoints when a cached keypoint CSV is not available.
- Pitch analysis that displays estimated velocity, extension, distance, and flight time.
- Biomechanics-related indicators calculated from pose keypoints, including joint-angle and arm-slot values.
- Visualizations for estimated spin and movement, pitch phases, and pitch trajectory.
- A pitch comparison view with synchronized video frames.
- A local analysis-history view with CSV and Excel export options.
- Optional upload of the saved local video file to an Amazon S3 bucket when an S3 bucket is configured.

### Not established by the current code

- The application does not demonstrate a publicly hosted service or a production deployment.
- The auto-tracking routine does not perform direct baseball detection: for new uploads, it generates an interpolated trajectory between a wrist-derived start point and a target point.
- Spin, break, and related pitch-quality metrics are model-based estimates, not direct measurements from a radar, high-speed tracking system, or instrumented ball.

## 4. How It Works

1. A user selects a video already in the local `videos/` directory or uploads an MP4/MOV clip. Uploaded files are saved locally first.
2. The analysis looks for per-video pose keypoints in `output/`. If they are unavailable, the application runs the bundled YOLO11 pose model over the video and writes keypoints to a CSV.
3. The application obtains release and net frame values from configured video data or user/application logic. Flight time is calculated from available tracking timestamps when present, otherwise from the frame interval and video frame rate.
4. Pitch speed and distance are calculated using project-specific formulas. The distance path differs for landscape and portrait video.
5. Pose-derived and model-derived indicators are displayed in the Streamlit interface. Results and intermediate files are stored locally under `output/`.
6. If `AWS_S3_BUCKET_NAME` is configured and AWS credentials are available through boto3's normal credential chain, the uploaded local video is also sent to S3. S3 is not used as the source for the app's analysis workflow.

For newly uploaded videos, the automatic tracking helper estimates release timing from wrist-keypoint movement and creates a simple interpolated ball path; this is not visual ball detection. Existing ball-tracking CSVs can be consumed by analysis code when present.

## 5. OpenCV and Computer Vision

OpenCV (`cv2`) is used for video frame access, frame dimensions and timing, image color conversion, and drawing visual overlays such as skeletons and ball-trajectory lines.

Pose estimation is performed by **Ultralytics YOLO11n-pose**, using the included `yolo11n-pose.pt` model. The pose module extracts COCO-style body keypoints and associates detections across frames using person location. Those keypoints feed the project's mechanics calculations and visualizations.

OpenCV itself does not provide the pose model, and the bundled YOLO model does not make the automatically generated ball path a detected ball trajectory. The current auto-tracker synthesizes that path from pose-derived coordinates and an assumed target.

## 6. AWS Integration (Amazon S3 video storage)

The S3 integration is optional and implemented in `src/aws_utils.py`. When a video is uploaded through the app, the file is saved in the local `videos/` directory. The app then attempts to upload that local file to the configured bucket under the key `videos/<filename>.mp4`.

The integration requires:

- `AWS_S3_BUCKET_NAME` set to the destination bucket name.
- AWS credentials available to boto3 through its standard provider chain, such as a local AWS profile or an attached IAM role.
- S3 permissions that allow uploading objects to the intended bucket and prefix.

`AWS_DEFAULT_REGION` can be set when needed; boto3 can also resolve a region through its normal configuration. The code does not pass credentials directly, download videos from S3, or use S3 for pose inference. If the bucket is not configured, the upload helper skips the S3 upload.

Never put AWS access keys, secret keys, session tokens, or other credentials in source code or commit them to the repository.

## 7. Technology Stack

- **Python**
- **Streamlit** and **Streamlit Authenticator**
- **Ultralytics YOLO11n-pose** for human pose estimation
- **OpenCV** for video and image processing
- **NumPy**, **pandas**, and **PyYAML**
- **Plotly** for interactive charts
- **boto3** for optional Amazon S3 uploads
- **Pillow**, **python-dotenv**, and **openpyxl**

Pinned Python dependencies are listed in [`requirements.txt`](requirements.txt).

## 8. Installation and Setup on Windows

Open PowerShell in the project directory. The commands below use the existing `requirements.txt` and create a project-local virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation due to the current execution policy, use the virtual environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The project expects `yolo11n-pose.pt` at the repository root (it is included in this project). For useful analysis, provide compatible videos and any required tracking/keypoint inputs in the expected local directories; sample videos and existing analysis data are not part of the Python package installation.

### Optional S3 setup

Configure AWS credentials outside the repository, for example with a local AWS CLI profile or an IAM role. Then, in PowerShell, set the bucket and optionally the region for the current terminal session:

```powershell
$env:AWS_S3_BUCKET_NAME = "your-bucket-name"
$env:AWS_DEFAULT_REGION = "your-aws-region"
# Optional when using a named local AWS profile:
$env:AWS_PROFILE = "your-profile-name"
```

Do not replace these values with access keys or secrets, and do not commit credential files. Without a configured bucket, local video analysis can proceed without the S3 upload.

## 9. How to Run the App

With the virtual environment active, run:

```powershell
streamlit run src/app.py
```

Alternatively, call Streamlit through the virtual environment directly:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/app.py
```

Streamlit prints the local address to open in a browser. The project code and configuration inspected for this README do not confirm a public deployment.

## 10. Project Structure

```text
.
├── src/
│   ├── app.py                         # Streamlit application
│   ├── aws_utils.py                   # Optional S3 upload helper
│   ├── pitch_logic.py                 # Pose processing, analysis, and visualizations
│   ├── pitch_speed_v23_auto_distance.py
│   │                                   # Pitch-speed and distance calculations
│   ├── result_logger.py               # Local result-history utility
│   ├── app_cli.py                     # Command-line analysis entry point
│   ├── gui_app.py                     # Additional GUI entry point
│   ├── baseball_3d_component.py       # 3D visualization component
│   ├── i18n.py                        # Localization strings and helpers
│   └── revenuecat_sdk.py              # RevenueCat integration code
├── videos/                            # Local input videos
├── output/                            # Generated keypoints, tracking, and results
├── yolo11n-pose.pt                    # YOLO pose model weights
├── config.example.yaml                # Example configuration template
├── .env.example                       # Example environment-variable template
└── requirements.txt                   # Pinned Python dependencies
```

Some files and directories, such as `videos/` and `output/`, are local working data and may need to be created or populated for a particular analysis.

## 11. Limitations and Future Improvements

### Current limitations

- Analysis quality depends on camera angle, frame rate, visibility, and pose-estimation accuracy.
- The auto-tracking helper estimates a release frame from wrist motion and generates an interpolated ball path; it does not detect the ball in each frame.
- Pitch velocity, extension, spin, and movement rely on project formulas, input availability, and assumptions. They should be treated as estimates.
- Some analysis paths expect per-video CSV data or configured frame information. A video upload alone does not guarantee that every measurement is based on independently detected events.
- S3 support currently uploads the local source video; it does not provide S3-based processing or retrieval.

### Possible future improvements

- Add validated ball detection and tracking from video rather than interpolating a trajectory.
- Calibrate camera geometry and validate estimates against reference measurement systems.
- Make input requirements and uncertainty more visible in the user interface.
- Add automated tests and documented evaluation datasets for analysis methods.
- Extend cloud storage workflows only with explicit access controls and user consent.

These are potential improvements, not claims about existing functionality.

## 12. Competition Context

Outpace Baseball is submitted to the **OpenCV AI Competition 2026** and is **powered by AWS**, with Amazon S3 used as an optional destination for uploaded video files. The computer-vision workflow combines OpenCV video handling with YOLO11 pose estimation; pitch-analysis outputs are calculated by project code from pose keypoints, frame timing, and available tracking data.

This README describes the implementation represented in the repository and does not claim competition results, official endorsement, or public hosting.
