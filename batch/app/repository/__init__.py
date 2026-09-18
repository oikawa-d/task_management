"""batchのrepository層パッケージ。

PostgreSQL・Redisへの直接アクセス（SQL実行、ストアドプロシージャ呼び出し、
Redis実行ロックの取得・解放）を集約する。api/app のrouter/serviceはimportしない。
"""
