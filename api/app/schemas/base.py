from pydantic import BaseModel, ConfigDict


class StrictSchema(BaseModel):
	"""未定義フィールドを拒否するDTOの共通基底。

	リクエストDTOでは想定外の入力フィールドを拒否し、レスポンスDTOでは
	定義済みフィールド以外が混入しないことを保証する。
	"""

	model_config = ConfigDict(extra="forbid")


__all__ = ["StrictSchema"]
