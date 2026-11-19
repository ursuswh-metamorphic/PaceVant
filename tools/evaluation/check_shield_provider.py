"""Check the configured Task Shield provider using benign text only, without wallet access."""

import json
import sys

from treasury_backend.core.errors import ControlError  # noqa: E402
from treasury_backend.modules.alignment.provider import ChatProvider, ShieldConfig, safe_text  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config = ShieldConfig.from_env("FUJI")
    provider = ChatProvider(config)
    try:
        value = provider.complete(
            [
                {"role": "system", "content": "Return one JSON object, no markdown."},
                {
                    "role": "user",
                    "content": "Trả lời bằng JSON gồm ok=true và lời chào ngắn bằng tiếng Việt. Đây chỉ là kiểm tra kết nối API, không dùng công cụ.",
                },
            ]
        )
        result = {
            "status": "CONNECTED",
            "config": config.public(),
            "latency_ms": value.latency_ms,
            "usage": value.usage,
            "output": safe_text(value.content),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ControlError as error:
        print(json.dumps({"status": "UNAVAILABLE", "code": error.code}))
        return 1
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
