from __future__ import annotations

import os
import unittest


PRIVATE_SAMPLE_ENV = "MEGIDO_RUN_PRIVATE_SAMPLE_TESTS"
PRIVATE_SAMPLE_TESTS_ENABLED = os.environ.get(PRIVATE_SAMPLE_ENV) == "1"
private_sample_test = unittest.skipUnless(
    PRIVATE_SAMPLE_TESTS_ENABLED,
    f"非公開サンプル検証です。実行するには {PRIVATE_SAMPLE_ENV}=1 を指定します。",
)
