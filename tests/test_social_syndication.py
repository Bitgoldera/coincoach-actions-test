from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.social_publishers import SocialSyndicator


class SocialSyndicationTests(unittest.TestCase):
    def make_image(self, root: Path) -> Path:
        image = root / "chart.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-image" * 100)
        return image

    def base_env(self, state_path: Path) -> dict[str, str]:
        return {
            "SOCIAL_SYNDICATION_ENABLED": "true",
            "SOCIAL_LIVE_APPROVED": "true",
            "SOCIAL_STATE_PATH": str(state_path),
            "SOCIAL_PENDING_RETRY_LIMIT": "0",
            "SOCIAL_REQUEST_TIMEOUT_SECONDS": "10",
            "DISCORD_PUBLISH_ENABLED": "false",
            "FACEBOOK_PUBLISH_ENABLED": "false",
            "INSTAGRAM_PUBLISH_ENABLED": "false",
            "THREADS_PUBLISH_ENABLED": "false",
        }

    def test_account_without_social_credentials_stays_binance_only(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json={"id": "unexpected"})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.make_image(root)
            env = self.base_env(root / "state.json")
            env.update({"SOCIAL_LIVE_APPROVED": "true"})
            with patch.dict(os.environ, env, clear=True):
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with SocialSyndicator(root, "account_01", client=client) as syndicator:
                    report = syndicator.publish_after_square(
                        caption="signal",
                        image_path=image,
                        signal={"symbol": "BTCUSDT", "timeframe": "15m"},
                    )
                client.close()

        self.assertEqual(report["status"], "disabled_no_platforms")
        self.assertEqual(calls, [])

    def test_missing_approval_blocks_all_social_calls(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json={"id": "unexpected"})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.make_image(root)
            env = self.base_env(root / "state.json")
            env.update(
                {
                    "SOCIAL_LIVE_APPROVED": "false",
                    "DISCORD_PUBLISH_ENABLED": "true",
                    "DISCORD_WEBHOOK_URL": "https://discord.test/api/webhooks/secret",
                }
            )
            with patch.dict(os.environ, env, clear=True):
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with SocialSyndicator(root, "account_02", client=client) as syndicator:
                    report = syndicator.publish_after_square(
                        caption="signal",
                        image_path=image,
                        signal={"symbol": "BTCUSDT", "timeframe": "15m"},
                    )
                client.close()

        self.assertEqual(report["status"], "blocked_missing_social_approval")
        self.assertEqual(calls, [])

    def test_discord_only_delivery_completes_and_cleans_pending_image(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.host, "discord.test")
            self.assertEqual(request.url.params.get("wait"), "true")
            return httpx.Response(200, json={"id": "discord-message-1"})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.make_image(root)
            state_path = root / "state" / "social.json"
            env = self.base_env(state_path)
            env.update(
                {
                    "DISCORD_PUBLISH_ENABLED": "true",
                    "DISCORD_WEBHOOK_URL": "https://discord.test/api/webhooks/secret",
                }
            )
            with patch.dict(os.environ, env, clear=True):
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with SocialSyndicator(root, "account_02", client=client) as syndicator:
                    report = syndicator.publish_after_square(
                        caption="BTC setup",
                        image_path=image,
                        signal={"symbol": "BTCUSDT", "timeframe": "15m"},
                    )
                client.close()

            state = json.loads(state_path.read_text(encoding="utf-8"))
            delivery = next(iter(state["deliveries"].values()))

        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(requests), 1)
        self.assertEqual(delivery["status"], "complete")
        self.assertEqual(delivery["platforms"]["discord"]["status"], "published")
        self.assertIsNone(delivery["retained_image_path"])

    def test_one_platform_failure_does_not_undo_other_platform_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if request.url.host == "discord.test":
                return httpx.Response(200, json={"id": "discord-ok"})
            if "api.cloudinary.com" in url:
                return httpx.Response(
                    200, json={"secure_url": "https://cdn.test/signal.png"}
                )
            if request.url.host == "graph.facebook.com":
                return httpx.Response(500, json={"error": {"message": "temporary"}})
            return httpx.Response(404, json={"error": "unexpected"})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.make_image(root)
            state_path = root / "state" / "social.json"
            env = self.base_env(state_path)
            env.update(
                {
                    "DISCORD_PUBLISH_ENABLED": "true",
                    "FACEBOOK_PUBLISH_ENABLED": "true",
                    "DISCORD_WEBHOOK_URL": "https://discord.test/api/webhooks/secret",
                    "FACEBOOK_PAGE_ID": "page-1",
                    "FACEBOOK_PAGE_ACCESS_TOKEN": "page-token",
                    "CLOUDINARY_CLOUD_NAME": "cloud",
                    "CLOUDINARY_API_KEY": "key",
                    "CLOUDINARY_API_SECRET": "secret",
                    "META_GRAPH_API_VERSION": "v99.0",
                }
            )
            with patch.dict(os.environ, env, clear=True):
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with SocialSyndicator(root, "account_02", client=client) as syndicator:
                    report = syndicator.publish_after_square(
                        caption="ETH setup",
                        image_path=image,
                        signal={"symbol": "ETHUSDT", "timeframe": "1h"},
                    )
                client.close()

            state = json.loads(state_path.read_text(encoding="utf-8"))
            delivery = next(iter(state["deliveries"].values()))
            retained = Path(delivery["retained_image_path"])
            retained_exists = retained.exists()

        self.assertEqual(report["status"], "partial_failure")
        self.assertEqual(delivery["platforms"]["discord"]["status"], "published")
        self.assertEqual(delivery["platforms"]["facebook"]["status"], "failed")
        self.assertEqual(delivery["status"], "pending_retry")
        self.assertTrue(retained_exists)
        self.assertEqual(delivery["public_image_url"], "https://cdn.test/signal.png")

    def test_meta_platform_requires_explicit_graph_version(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.cloudinary.com":
                return httpx.Response(
                    200, json={"secure_url": "https://cdn.test/signal.png"}
                )
            return httpx.Response(500, json={"error": "should not call graph"})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.make_image(root)
            env = self.base_env(root / "state.json")
            env.update(
                {
                    "FACEBOOK_PUBLISH_ENABLED": "true",
                    "FACEBOOK_PAGE_ID": "page-1",
                    "FACEBOOK_PAGE_ACCESS_TOKEN": "page-token",
                    "CLOUDINARY_CLOUD_NAME": "cloud",
                    "CLOUDINARY_API_KEY": "key",
                    "CLOUDINARY_API_SECRET": "secret",
                }
            )
            with patch.dict(os.environ, env, clear=True):
                client = httpx.Client(transport=httpx.MockTransport(handler))
                with SocialSyndicator(root, "account_02", client=client) as syndicator:
                    report = syndicator.publish_after_square(
                        caption="SOL setup",
                        image_path=image,
                        signal={"symbol": "SOLUSDT", "timeframe": "4h"},
                    )
                client.close()

        self.assertEqual(report["status"], "disabled_no_platforms")


if __name__ == "__main__":
    unittest.main()

