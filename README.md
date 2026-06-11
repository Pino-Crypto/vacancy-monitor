# 東横イン那覇 空室監視(楽天トラベルAPI × LINE通知)

那覇市内の東横イン4店舗について、2026-07-04〜07-09(1名・禁煙)の空室を
10分おきにチェックし、空きが出た瞬間にLINEへ通知します。

- データ取得は楽天トラベルの公式API(無料)を使用 — スクレイピングではありません
- 監視システム自体が壊れた場合(3回連続エラー)もLINEに通知します
- 予約は通知のリンクから手動で行います(自動予約はしません)

## セットアップ(所要15〜20分)

### 1. 楽天ウェブサービスのアプリIDを取得(無料)

1. https://webservice.rakuten.co.jp/ にアクセスし、楽天IDでログイン
2. 「アプリID発行」から新規アプリを登録(名前は何でもOK、URLは GitHub リポジトリのURLでOK)
3. 発行された **アプリID**(数字列)と**アクセスキー(applicationSecret)**の両方を控える
   (後から確認する場合は「アプリ情報の確認(Your Apps)」から。アクセスキーは他人に見せないこと)

### 2. LINE Messaging API の設定

1. https://developers.line.biz/ja/ にLINEアカウントでログイン
2. プロバイダーを新規作成 → チャネルを「Messaging API」で作成
3. LINE Official Account Manager 側で「チャネルアクセストークン(長期)」を発行して控える
4. チャネル設定画面のQRコードを自分のLINEで読み取り、**友だち追加する**
   (このbotの友だちは自分だけにしてください。通知はbroadcast配信のため友だち全員に届きます)
5. 応答設定で「あいさつメッセージ」「応答メッセージ」はオフ推奨

### 3. GitHubリポジトリの設定

1. このフォルダの中身を公開リポジトリとしてpush
2. リポジトリの Settings → Secrets and variables → Actions で以下を登録:
   - `RAKUTEN_APP_ID` : 手順1のアプリID(数字)
   - `RAKUTEN_ACCESS_KEY` : 手順1のアクセスキー(applicationSecret)
   - `LINE_CHANNEL_ACCESS_TOKEN` : 手順2のトークン
3. Actions タブ → `vacancy-check` → 「Run workflow」で手動実行してテスト
4. 成功すれば、以後10分おきに自動実行されます

※ トークン類はすべてSecretsに保存されるため、リポジトリを公開しても漏れません。
   コード内に秘密情報を書かないでください。

## 監視対象の変更

`monitor.py` 冒頭の設定を書き換えます。

- 日付: `CHECKIN` / `CHECKOUT`
- 店舗: `HOTELS`(楽天トラベルのホテルページURLに含まれる番号がホテル番号です)
- 人数: `ADULTS`

## 停止方法

予約が取れたら、リポジトリの Actions タブから `vacancy-check` ワークフローを
Disable するか、`check.yml` の schedule をコメントアウトしてください。

## 注意事項

- 楽天トラベルと東横イン公式サイトは在庫が別管理です。公式サイト側のみの
  空きは検知できないため、公式サイトは適宜手動で確認してください。
- LINE無料プランの送信上限は月200通です(この設計では通常問題になりません)。
- GitHub Actions の cron は数分遅延することがあります。
