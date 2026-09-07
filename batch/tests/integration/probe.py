import asyncio
import os

import redis.asyncio as redis
from app.db import get_db_engine
from sqlalchemy import text


async def _verify_postgres() -> None:
	engine = get_db_engine()
	try:
		async with engine.connect() as connection:
			result = await connection.execute(text("SELECT 1"))
			assert result.scalar_one() == 1
	finally:
		await engine.dispose()


async def _verify_redis() -> None:
	client = redis.from_url(os.environ["REDIS_URL"])
	try:
		assert await client.ping()
	finally:
		await client.aclose()


async def main() -> None:
	await _verify_postgres()
	await _verify_redis()


if __name__ == "__main__":
	asyncio.run(main())
