"""アプリ全体で共有する定数定義モジュール。

文字列長の上限値やトークン長など、複数レイヤーから参照される固定値を集約する。
"""

import base64

EMAIL_MAX_LENGTH = 254
DESCRIPTION_MAX_LENGTH = 2000
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
AUTH_TOKEN_MAX_LENGTH = 512
TOKEN_URLSAFE_BYTES = 32
TOKEN_URLSAFE_LENGTH = len(base64.urlsafe_b64encode(b"\0" * TOKEN_URLSAFE_BYTES).rstrip(b"="))
