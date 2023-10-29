Controller
===

Instance の状態を LED に表示、その連携の停止、画像を LED で表現するといった API を持ちます。

また、そのバックグラウンドでは Firestore の **instance** コレクションからデータを取得し、  
各 LED がステータスに応じ色が変化するようデータに整形、**led** コレクションに保存します。

- **ACTIVE**: 緑
- **IDLE**: 黄
- **TERMINATED**: 赤
