"""
Quick smoke test: verifies the .mp4 file-type fix.
Run: python scripts/test_video_upload.py
"""
import http.client
import json

BASE_HOST = "localhost"
BASE_PORT = 8000

# Minimal fake MP4 (ftyp box magic bytes) — enough to pass file-type check
mp4_bytes = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41' + b'\x00' * 200

boundary = "----TestBoundary7890"
body_parts = [
    f"--{boundary}\r\n".encode(),
    b"Content-Disposition: form-data; name=\"file\"; filename=\"test.mp4\"\r\n",
    b"Content-Type: video/mp4\r\n\r\n",
    mp4_bytes,
    f"\r\n--{boundary}\r\n".encode(),
    b"Content-Disposition: form-data; name=\"camera_id\"\r\n\r\nCAM_001",
    f"\r\n--{boundary}\r\n".encode(),
    b"Content-Disposition: form-data; name=\"frame_skip\"\r\n\r\n10",
    f"\r\n--{boundary}--\r\n".encode(),
]
body = b"".join(body_parts)

print("Testing POST /process/video with .mp4 file...")
conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
conn.request(
    "POST", "/process/video",
    body=body,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    },
)
resp = conn.getresponse()
raw  = resp.read()
conn.close()

print(f"HTTP Status : {resp.status}")
try:
    data = json.loads(raw)
    print(f"Response    : {json.dumps(data)[:300]}")
except Exception:
    print(f"Response    : {raw[:200]}")

print()
if resp.status == 415:
    print("RESULT : FAIL — still getting 415 Unsupported Media Type")
    print("         The fix did not take effect. Check image_service.py")
elif resp.status in (200, 422, 500):
    print("RESULT : PASS — .mp4 passed the file-type validator")
    print(f"         HTTP {resp.status} means the video was accepted (processing")
    print(f"         may fail on fake data but the 415 error is GONE)")
else:
    print(f"RESULT : HTTP {resp.status} — unexpected status")
