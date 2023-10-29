LED によるコンテナのスケール可視化
===

Kubernetes (GKE) または Cloud Run のコンテナを監視し、その状況を LED で可視化します。

## デモ

デモ参加者は QR コードからサイトにアクセスすることで負荷かけツールが起動、コンテナがスケールし始めます。  
しばらくすると、増えていくコンテナに応じて LED パネルが光り始めます。


## コンポーネント

### クラウド側

- **Instance**: GKE または Cloud Run 上で稼働するサンプルプログラム。自分自身の状態を一定周期で Firestore に保存
- **Controller**: LED 制御機能 + バックグラウンドで Instance の状態を LED 用のデータに整形 Firestore に書き込み
- **K8s**: Instance や Controller を Kubernetes 上にデプロイするためのマニフェスト
- **Load-Gen**: Hey を使って GKE や Cloud Run に対して負荷を生成

### LED 側

- **Raspberry Pi**: 毎秒 Firestore から LED 用のデータを読み込み、Teensy に送信
- **Teensy**: 受け取ったデータに基づき LED パネルを制御

### Web UI（LED シミュレーション）

- **UI**: GKE 用
- **UI-CR**: Cloud Run 用


## デモ環境セットアップ

### クラウドの基本設定

1. 有効な請求先アカウントとプロジェクトを作成

2. ローカル クライアントの認証

```sh
gcloud auth login
gcloud config set project <your-project-id>
```

3. 利用サービスの有効化

```sh
gcloud services enable compute.googleapis.com firestore.googleapis.com \
    container.googleapis.com run.googleapis.com artifactregistry.googleapis.com
```

4. Firestore データベースの作成

```sh
gcloud app create --region "asia-northeast1"
gcloud firestore databases create --database "demo" --type "firestore-native" --location "asia-northeast1"
```

5. Artifact Registry にリポジトリを作成

```sh
gcloud artifacts repositories create demo \
    --repository-format "docker" --location "asia-northeast1" \
    --description "Docker repository for demo apps"
```

### Instance コンテナ

1. ローカル確認用に、認証情報を生成

```sh
gcloud auth application-default login
```

2. アプリケーションをビルドし、ローカルで起動

```sh
docker build -t instance instance/
docker run --name instance -d --rm -u $(id -u):$(id -g) -p 8080:8080 \
    -v "${HOME}/.config/gcloud:/gcp/config:ro" -e CLOUDSDK_CONFIG=/gcp/config \
    -e GOOGLE_APPLICATION_CREDENTIALS=/gcp/config/application_default_credentials.json \
    -e PROJECT_ID=$( gcloud config get-value project ) -e FIRESTORE_DATABASE=demo \
    -e INSTANCE_COLLECTION=cr-instances -e HOSTNAME=instance instance
```

3. API にアクセス、挙動を確認

```sh
time curl -iXGET localhost:8080/wait?s=5
curl -iXGET localhost:8080/status
docker logs -f instance
docker stop instance
```

4. Firestore 上のデータを確認

[Firestore コンソール](https://console.cloud.google.com/firestore/databases/demo/) にアクセスし、確認してみましょう。

5. Artifact Registry への push

問題がなさそうであれば Artifact Registry へ docker push します。

```sh
repo="asia-northeast1-docker.pkg.dev/$( gcloud config get-value project )/demo"
docker tag instance "${repo}/instance:v0.5"
gcloud auth configure-docker asia-northeast1-docker.pkg.dev
docker push "${repo}/instance:v0.5"
```

### Controller コンテナ

1. アプリケーションをビルドし、ローカルで起動

```sh
docker build -t controller controller/
docker run --name controller -d --rm -u $(id -u):$(id -g) -p 8000:8000 \
    -v "${HOME}/.config/gcloud:/gcp/config:ro" -e CLOUDSDK_CONFIG=/gcp/config \
    -e GOOGLE_APPLICATION_CREDENTIALS=/gcp/config/application_default_credentials.json \
    -e PROJECT_ID=$( gcloud config get-value project ) -e FIRESTORE_DATABASE=demo \
    -e INSTANCE_COLLECTION=cr-instances -e LED_COLLECTION=cr \
    -e GAMMA="1.0" controller
```

2. Web にアクセス、挙動を確認

http://localhost:8000/

ログも確認し、問題がなければ停止します。

```sh
docker logs -f controller
docker stop controller
```

3. Firestore 上のデータを確認

[Firestore コンソール](https://console.cloud.google.com/firestore/databases/demo/) にアクセスし、確認してみましょう。

4. Artifact Registry への push

問題がなさそうであれば Artifact Registry へ docker push します。

```sh
docker tag controller "${repo}/controller:v0.5"
docker push "${repo}/controller:v0.5"
```

### Instance on Cloud Run

1. アプリケーション用のサービスアカウントを作成

```sh
gcloud iam service-accounts create demo-apis \
    --display-name "SA for demo apis" \
    --description "Service Account for demo APIs"
export project_id=$( gcloud config get-value project )
gcloud projects add-iam-policy-binding "${project_id}" \
    --member "serviceAccount:demo-apis@${project_id}.iam.gserviceaccount.com" \
    --role "roles/datastore.user"
```

2. Instance サービスのデプロイ

```sh
gcloud run deploy demo-instance --platform "managed" --region "asia-northeast1" \
    --image "${repo}/instance:v0.5" --cpu 1.0 --memory 512Mi --no-cpu-throttling \
    --concurrency 3 --min-instances 0  --max-instances 1000 \
    --ingress "internal-and-cloud-load-balancing" --allow-unauthenticated \
    --set-env-vars "PROJECT_ID=${project_id},FIRESTORE_DATABASE=demo,INSTANCE_COLLECTION=cr-instances,LED_COLLECTION=cr" \
    --service-account "demo-apis@${project_id}.iam.gserviceaccount.com"
```

3. ロードバランサーの設置

VPC ネットワーク、プロキシ専用サブネットを作ります。

```sh
gcloud compute networks create demo-network --subnet-mode "custom"
gcloud compute networks subnets create demo-tokyo --network "demo-network" \
    --range "10.1.2.0/24" --region "asia-northeast1"
gcloud compute networks subnets create proxy-only-subnet \
    --purpose "REGIONAL_MANAGED_PROXY" --role "ACTIVE" \
    --network "demo-network" --region "asia-northeast1" \
    --range "10.129.0.0/23"
```

接続先の静的 IP アドレスを確保しつつ、

```sh
gcloud compute addresses create demo-instance-cr  \
    --region "asia-northeast1" --network-tier "STANDARD"
```

HTTP で接続可能なロードバランサを設置します。

```sh
gcloud compute network-endpoint-groups create neg-instance-cr \
    --region "asia-northeast1" --network-endpoint-type "serverless" \
    --cloud-run-service "demo-instance"
gcloud compute backend-services create demo-instance-cr --region "asia-northeast1" \
    --load-balancing-scheme "EXTERNAL_MANAGED" --protocol "HTTP"
gcloud compute backend-services add-backend demo-instance-cr --region "asia-northeast1" \
    --network-endpoint-group "neg-instance-cr" \
    --network-endpoint-group-region "asia-northeast1"
gcloud compute url-maps create url-instance-cr --region "asia-northeast1" \
    --default-service "demo-instance-cr" 
gcloud compute target-http-proxies create proxy-instance-cr \
    --region "asia-northeast1" --url-map "url-instance-cr"
gcloud compute forwarding-rules create demo-instance-cr \
    --load-balancing-scheme "EXTERNAL_MANAGED" --network-tier "STANDARD" \
    --region "asia-northeast1" --network "demo-network" \
    --target-http-proxy-region "asia-northeast1" \
    --address "demo-instance-cr" --ports "80" \
    --target-http-proxy "proxy-instance-cr"
echo "http://$( gcloud compute addresses describe demo-instance-cr \
    --region "asia-northeast1" --format json | jq -r .address )/"
```

### Instance on GKE

1. GKE Standard クラスタの作成

```sh
gcloud container clusters create demo --release-channel "stable" \
    --machine-type "e2-standard-4" --num-nodes 1 --min-nodes 1 --max-nodes 100 \
    --enable-autoscaling --workload-pool="${project_id}.svc.id.goog" \
    --network "demo-network" --subnetwork "demo-tokyo" --zone "asia-northeast1-c" \
    --gateway-api "standard" --enable-image-streaming
```

2. Workload Identity 経由でのアプリ用サービスアカウント利用を許可

```sh
gcloud iam service-accounts add-iam-policy-binding \
    "demo-apis@${project_id}.iam.gserviceaccount.com" \
    --member "serviceAccount:${project_id}.svc.id.goog[default/demo-apis]" \
    --role roles/iam.workloadIdentityUser
```

3. デプロイ

環境依存の設定値をファイルに書き出し、

```txt
cat << EOF >k8s/instance/setters.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: setters
data:
  project-id: "${project_id}"
  image-id: "asia-northeast1-docker.pkg.dev/${project_id}/demo/instance:v0.5"
  k-service-account: "demo-apis"
  g-service-account: "demo-apis@${project_id}.iam.gserviceaccount.com"
EOF
```

Kpt でレンダリングしたマニフェストを apply します。

```sh
kpt fn render k8s/instance/ -o unwrap | kubectl apply -f -
```

4. LB & HPA の設置

```sh
kubectl apply -f k8s/instance-lb
```

ロードバランサが設定されるまで数分かかります。  
しばらくしてから以下のコマンドで得られる URL にアクセスし、応答があることを確認します。

```sh
echo "http://$( kubectl get gateways.gateway.networking.k8s.io instance -o json \
    | jq -r ".status.addresses[0].value" )/status"
```

### Controllers on GKE

GKE と Cloud Run、それぞれの Controller を GKE 上にデプロイします。  
環境依存の設定値をファイルに書き出し、

```txt
cat << EOF >k8s/controller/setters.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: setters
data:
  project-id: "${project_id}"
  image-id: "asia-northeast1-docker.pkg.dev/${project_id}/demo/controller:v0.5"
  k-service-account: "demo-apis"
EOF
```

Kpt でレンダリングしたマニフェストを apply します。

```sh
kpt fn render k8s/controller/ -o unwrap | kubectl apply -f -
```

ロードバランサが設定されるまで数分かかります。  
しばらくしてから以下のコマンドで得られる URL にアクセスしてみましょう。

```sh
echo "http://$( kubectl get services controller-cloudrun \
   -o jsonpath='{.status.loadBalancer.ingress[0].ip}' )/"
echo "http://$( kubectl get services controller-gke \
   -o jsonpath='{.status.loadBalancer.ingress[0].ip}' )/"
```

### Load generators on Cloud Run

1. アプリケーションの確認

```sh
docker build -t loadgen load-gen/
docker run --name loadgen -d --rm -p 9000:9000 \
    -e PROJECT_ID=$( gcloud config get-value project ) -e PORT=9000 \
    -e URL="http://$( gcloud compute addresses describe demo-instance-cr \
        --region 'asia-northeast1' --format 'json' | jq -r '.address' )/wait?s=3" \
    -e REQUEST=1000 -e CONCURRENCY=100 -e DURATION=30 -e TIMEOUT=10 \
    -e ENVIRONMENT='Cloud Run' loadgen
```

Web にアクセスし、負荷をかけてみます。

http://localhost:9000/

問題がなければ停止します。

```sh
docker stop loadgen
```

2. Artifact Registry への push

```sh
repo="asia-northeast1-docker.pkg.dev/$( gcloud config get-value project )/demo"
docker tag loadgen "${repo}/loadgen:v0.5"
docker push "${repo}/loadgen:v0.5"
```

3. Load generator サービスのデプロイ

Cloud Run への負荷かけサービスをデプロイします。

```sh
gcloud run deploy demo-loadgen-cr --platform "managed" --region "asia-northeast1" \
    --image "${repo}/loadgen:v0.5" --cpu 4.0 --memory 2Gi \
    --concurrency 1 --min-instances 0  --max-instances 10 \
    --set-env-vars "PROJECT_ID=${project_id},ENVIRONMENT='Cloud Run',URL=http://$( gcloud compute \
        addresses describe demo-instance-cr --region 'asia-northeast1' --format 'json' \
        | jq -r '.address' )/wait?s=3,REQUEST=1000,CONCURRENCY=100,DURATION=30,TIMEOUT=10" \
    --allow-unauthenticated
```

GKE への負荷かけサービスもデプロイします。

```sh
gcloud run deploy demo-loadgen-gke --platform "managed" --region "asia-northeast1" \
    --image "${repo}/loadgen:v0.5" --cpu 4.0 --memory 2Gi \
    --concurrency 1 --min-instances 0  --max-instances 10 \
    --set-env-vars "PROJECT_ID=${project_id},ENVIRONMENT=GKE,URL=http://$( kubectl get \
        gateways.gateway.networking.k8s.io instance -o json \
        | jq -r ".status.addresses[0].value" )/wait?s=3,REQUEST=1000,CONCURRENCY=100,DURATION=30,TIMEOUT=10" \
    --allow-unauthenticated
```

### Web UI（LED シミュレーション）on Firebase

https://console.firebase.google.com/ にアクセスし、Firebase プロジェクトを作成します。 

1. CLI のインストール・認証

```sh
npm install -g firebase-tools
firebase login --no-localhost
```

2. プロジェクト ID を設定ファイルに保存

```txt
export project_id=$( gcloud config get-value project )
sed "s/project-id/${project_id}/" ui/.firebaserc.template > ui/.firebaserc
sed "s/project-id/${project_id}/" ui/firebase.json.template > ui/firebase.json
sed "s/project-id/${project_id}/" ui-cr/.firebaserc.template > ui-cr/.firebaserc
sed "s/project-id/${project_id}/" ui-cr/firebase.json.template > ui-cr/firebase.json
```

3. UI for Cloud Run のビルドとデプロイ

Firebase Hosting に新規サイトを追加します。

```sh
firebase hosting:sites:create "${project_id}-led-cloudrun" --project "${project_id}"
```

Firebase コンソール `プロジェクトの設定` から Web アプリ `ui-cr` を追加し、  
`ui/src/app.js` の設定値を書き換え、ビルドします。

```sh
cd ui-cr
npm install
npm run build
firebase deploy
cd ..
```

4. UI for GKE のビルドとデプロイ

Firebase Hosting に新規サイトを追加します。

```sh
firebase hosting:sites:create "${project_id}-led-gke" --project "${project_id}"
```

Firebase コンソール `プロジェクトの設定` から Web アプリ `ui` を追加し、  
`ui/src/app.js` の設定値を書き換え、ビルドします。

```sh
cd ui
npm install
npm run build
firebase deploy
cd ..
```
