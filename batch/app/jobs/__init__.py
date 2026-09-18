"""batchのジョブ本体パッケージ。

APSchedulerから起動される各定期ジョブ（実行契機の判定、Redisロック制御、
batch_historyへの実行記録）を格納する。
"""
