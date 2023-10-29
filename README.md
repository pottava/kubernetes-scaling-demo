LED によるコンテナのスケール可視化
===

Kubernetes または Cloud Run のコンテナを監視し、その状況を LED で可視化します。

## デモ

デモ参加者は QR コードからサイトにアクセスすることで負荷かけツールが起動、GKE や Cloud Run がスケールし始めます。  
しばらくすると、LED パネルが増えていくコンテナに応じて光り始めます。


## コンポーネント

### クラウド側

- Instance: Kubernetes または Cloud Run 上で稼働するサンプルプログラム。自分自身の状態を一定周期で Firestore に登録
- Controller: Instance の状態を Firestore から読み込み、LED 用のデータに整形、Firestore の別コレクションに書き込み
- k8s: Instance や Controller を Kubernetes 上にデプロイするためのマニフェスト
- Load-Gen: Hey を使って GKE や Cloud Run に対して負荷を生成

### LED 側

- Raspberry Pi: 毎秒 Firestore から LED 用のデータを読み込み、Teensy に送信
- Teensy: 受け取ったデータに基づき LED パネルを制御

### Web UI（LED シミュレーション）

- UI: GKE 用
- UI-CR: Cloud Run 用
