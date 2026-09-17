#!/bin/sh -e

alembic upgrade head
exec "$@"
