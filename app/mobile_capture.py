from __future__ import annotations

import os
import time
from pathlib import Path

import yaml
from PIL import Image


class MobileCaptureError(RuntimeError):
    pass


class BinanceMobileCapture:
    """
    Remote cloud-Android chart capture.

    This worker intentionally uses configuration-driven coordinates because Binance app
    selectors and layouts vary by release. Calibrate against one fixed cloud device,
    then keep that resolution/version pinned.
    """

    def __init__(self, root: Path, settings: dict) -> None:
        self.root = root
        self.settings = settings
        calibration_path = root / settings["capture"]["calibration_file"]
        with calibration_path.open("r", encoding="utf-8") as handle:
            self.calibration = yaml.safe_load(handle)

    def capture(self, symbol: str, timeframe: str, output_path: Path) -> Path:
        if not self.settings["capture"]["enabled"]:
            raise MobileCaptureError("Mobile capture is disabled. Set MOBILE_CAPTURE_ENABLED=true after calibration.")

        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
        except ImportError as exc:
            raise MobileCaptureError("Appium client is not installed") from exc

        appium_cfg = self.settings["capture"]["appium"]
        server_url = os.getenv(appium_cfg["server_url_env"], "")
        if not server_url:
            raise MobileCaptureError("APPIUM_SERVER_URL is missing")
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.device_name = os.getenv(appium_cfg["device_name_env"], "CoinCoachCloudAndroid")
        platform_version = os.getenv(appium_cfg["platform_version_env"], "")
        if platform_version:
            options.platform_version = platform_version
        app_package = os.getenv(appium_cfg["app_package_env"], "")
        app_activity = os.getenv(appium_cfg["app_activity_env"], "")
        if app_package:
            options.app_package = app_package
        if app_activity:
            options.app_activity = app_activity
        options.no_reset = True
        driver = webdriver.Remote(server_url, options=options)
        try:
            time.sleep(float(self.calibration.get("launch_wait_seconds", 5)))
            coords = self.calibration["coordinates"]
            self._tap(driver, coords.get("dismiss_popup"), optional=True)
            self._tap(driver, coords["markets_tab"])
            self._tap(driver, coords["search_button"])
            self._tap(driver, coords["search_input"])
            driver.switch_to.active_element.send_keys(symbol.replace("USDT", ""))
            time.sleep(2)
            self._tap(driver, coords["first_search_result"])
            time.sleep(3)
            self._tap(driver, coords["chart_tab"])
            time.sleep(2)
            self._tap(driver, coords["timeframe_button"])
            self._tap(driver, coords["timeframe_menu"][timeframe])
            time.sleep(3)

            raw_path = output_path.with_suffix(".raw.png")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(str(raw_path))
            crop = tuple(self.settings["capture"]["crop_box"])
            with Image.open(raw_path) as image:
                cropped = image.crop(crop)
                cropped.save(output_path, format="PNG", optimize=True)
            raw_path.unlink(missing_ok=True)
            minimum = int(self.calibration.get("validation", {}).get("minimum_image_bytes", 90000))
            if output_path.stat().st_size < minimum:
                raise MobileCaptureError("Captured image is unexpectedly small; chart may not have loaded")
            return output_path
        finally:
            driver.quit()

    @staticmethod
    def _tap(driver, point, optional: bool = False) -> None:
        if not point:
            if optional:
                return
            raise MobileCaptureError("Missing required calibration coordinate")
        driver.tap([(int(point[0]), int(point[1]))], 120)
