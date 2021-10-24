# stella_bot

## 概要
- https://stellabms.xyz/ の新規提案・修正提案・現行難度表のスクレイピングをします。
- スクレイピングで得たデータをもとにGoogleスプレッドシートを生成します。
- Discord botにメンションを送ることで、各楽曲に対してコメントが付けられます。コメントはスプレッドシートに即時反映されます。

## 使い方
`python stella_bot.py`

`stella_scraper.py`はサイトのスクレイピングとDB更新のみ担うので、Discord bot部とは完全に独立しています。`stella_bot.py`から呼んで使用。

実際には`Restart=on-success`としたsystemctlのserviceとしています。

## Discord botへのメンション記法
### 新規コメントの追加
![image](https://user-images.githubusercontent.com/36487148/138576582-ad0dfbef-0572-484e-bd61-9ebc1584cc69.png)

こんな感じ。

- 1行目 = @stella_bot+半角スペース+難度+半角スペース+曲名
- 2行目以降 = コメント(何行あってもいい)

DP SATTELITEの難度表記はdp0のように(sl表記だとSPと区別が出来ないので)。画像も添付できます。

🆕のリアクションがつきます。

### コメントの修正
既にコメント投稿済みの譜面について、再投稿すれば勝手に上書きされます。

🆙のリアクションがつきます。

### コメントの削除
コメントの修正において、コメントの内容を"削除"(ダブルクオートは不要)とすれば良いです。

💥 のリアクションがつきます。

## その他
内輪向けなので詳しいマニュアルなどをgithub上に作る予定はありません。ごめんなさい。
