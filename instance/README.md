Instance
===

Kubernetes または Cloud Run で稼働するサンプル アプリケーション、REST API サーバーです。  
`/sqrt` や `/pi` など URI に応じて 1,000,000 程度まで無駄に重い計算を行い、結果を返します。

バックグラウンドでは 3 秒おきに処理中のリクエスト数を監視し、  
Firestore の **instance** コレクションに以下のいずれかのステータスを書き込みます。

- **ACTIVE**: リクエスト処理中
- **IDLE**: 処理中のリクエストなし
- **TERMINATED**: プロセス停止中
