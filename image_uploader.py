"""
Image upload utility module using ImgBB API.
"""

import requests
import config


def upload_to_imgbb(image_path: str, expiration: int = 30) -> str:
    """
    Upload a local image to ImgBB with an auto-expiration TTL.

    :param image_path: Path to the image file.
    :param expiration: Auto-delete time in seconds (default: 30).
    :return: Direct URL string if upload succeeds, None otherwise.
    """
    url = "https://api.imgbb.com/1/upload"
    api_key = config.IMGBB_API_KEY

    if not api_key:
        print("[Error] IMGBB_API_KEY is not configured in environment variables.")
        return None

    try:
        with open(image_path, "rb") as image_file:
            data = {"key": api_key}
            files = {
                "image": image_file,
                "expiration": expiration
            }
            response = requests.post(url, data=data, files=files, timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {}).get("url")
        else:
            print(f"[Error] ImgBB upload failed: {response.json()}")
            return None
    except Exception as exc:
        print(f"[Error] Exception occurred while uploading to ImgBB: {exc}")
        return None