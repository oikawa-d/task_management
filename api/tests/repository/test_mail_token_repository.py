import json
import uuid
from unittest.mock import AsyncMock

import pytest
from app.repository.mail_token_repository import MailTokenRepository


@pytest.mark.asyncio
async def test_save_email_token_stores_hash_and_ttl_without_plaintext() -> None:
	redis = AsyncMock()
	repository = MailTokenRepository(redis)
	token = "email-token"
	user_id = uuid.uuid4()

	await repository.save_email_verification_token(token, user_id, ttl=600)

	arguments = redis.eval.await_args.args
	assert token not in arguments
	assert repository.hash_token(token) in arguments
	assert "600" in arguments


@pytest.mark.asyncio
async def test_consume_password_reset_token_requires_current_hash_and_is_one_time() -> None:
	redis = AsyncMock()
	user_id = uuid.uuid4()
	redis.eval.return_value = json.dumps({"user_id": str(user_id)}).encode()
	repository = MailTokenRepository(redis)

	result = await repository.consume_password_reset_token("reset-token")

	assert result == user_id
	arguments = redis.eval.await_args.args
	assert "reset-token" not in arguments
	assert repository.hash_token("reset-token") in arguments


@pytest.mark.asyncio
async def test_consume_email_verification_token_uses_atomic_getdel() -> None:
	redis = AsyncMock()
	user_id = uuid.uuid4()
	redis.getdel.return_value = json.dumps({"user_id": str(user_id)}).encode()
	repository = MailTokenRepository(redis)

	assert await repository.consume_email_verification_token("verify-token") == user_id
	redis.getdel.assert_awaited_once_with("emailverify:" + repository.hash_token("verify-token"))


@pytest.mark.asyncio
async def test_revoke_all_sessions_and_refresh_tokens_removes_every_member() -> None:
	redis = AsyncMock()
	redis.smembers.side_effect = [{b"session-a", b"session-b"}, {b"refresh-a"}]
	repository = MailTokenRepository(redis)
	user_id = uuid.uuid4()

	assert await repository.delete_all_sessions(user_id) == 2
	assert await repository.revoke_all_refresh_tokens(user_id) == 1

	delete_calls = [call.args for call in redis.delete.await_args_list]
	session_call = next(call for call in delete_calls if f"user_sessions:{user_id}" in call)
	assert set(session_call[:-1]) == {"session:session-a", "csrf:session-a", "session:session-b", "csrf:session-b"}
	assert ("refresh:refresh-a", f"user_refresh:{user_id}") in delete_calls
