# 実験終了からremote観測まで

`CONFIRM=YES make probe` / `CONFIRM=YES make turn` / `CONFIRM=YES make experiment` は、それぞれ明示的に選択された実験を1回だけ実行し、成功でも失敗でも保存済みrunの公開処理へ進む。別モードの実行・自動再試行・次TURN数への進行はしない。API実験の許可は別途必要。

1. 実験前にmain/master・detached HEAD・origin不在・未commit実装・既存staged変更を検査し、問題があればAPI消費前に停止。
2. 既存の無料check、API予算・retryガードで指定実験だけを実行する。予定表示の`execution_started: false`は完了の証拠ではない。
3. 成功・失敗の原本を保存後、sanitize（公開用の最小項目への投影）・secret scan・監査validation・status生成。未検証secretを黙って削って公開せず、既存のfail-closed規則で拒否する。
4. 対象run_idがlatestとして公開されたこと、チェックのsource digestが一致することを確認。新たなAPIは呼ばない。
5. results/statusとRESEARCH_STATE.mdだけをcommit。原本・checkpoint・未commit実装を自動で含めない。
6. outgoing commitを再検証して現在branchへpush。main/masterは禁止。
7. git fetch origin後、HEAD、origin/branch、git ls-remoteの広告SHAを比較。開始branchから切り替わっていても拒否。
8. 一致を確認した場合のみ`REMOTE OBSERVABILITY READY: <commit>`を表示する。失敗実験でも観測公開自体は成功できる。実験の失敗exit codeは保持する。

途中で同期が失敗した場合は非ゼロ終了。`results/debug/publication-receipt.json`にPASS/FAIL/PENDINGと安全な固定エラーコードを保存する（このreceiptはGit対象外）。修復後は **make sync-statusだけ** を実行する。これは保存済み結果の検証・公開だけで、probe/1TURN/8TURNを一切実行しない。新しい実装変更があるなら先に通常の検証・commitを行う。

GitHubを読む側は対象branchのHEADとlatest.jsonを読む。latest.jsonの`commit`は生成前のソースHEADであり、公開commit自身のSHAではない。この違いを「未push」と混同しない。公開commit自身はbranch refやGitHub APIで確認する。

## 今回の調査結果

調査開始HEAD f81da80833c9aac4719134edac9bdf5b1374f054にはprobe `20260917T022330Z-a9d78ed9` が既に含まれていた。新しいfresh 1TURNの原本は本checkout・登録worktree・results/finalを含む保存JSON/監査/checkpointの調査では見つかっていない。run_idまたは別の保存先の確認が必要であり、1TURN成功や8TURN READYを推測してはいけない。

旧実装は実験終了時にprepareのみ実行してcommit/pushせず、その失敗も表示だけで終了していた。旧make sync-statusが正常完了すればcommit/pushする設計だったが、fetch/remote照合はなかった。過去のコマンド実行ログがないため、個々の未同期をGitHubの伝播遅延やpush失敗と決めつけることはできない。今回確認できた新probe自体はすでに同期済みで、新1TURNの欠落をpublication障害だけでは説明できない。

今回追加した自動公開・remote照合は、この曖昧さを解消する。保存されていないrunを作ったことにしたり、実験を再実行して穴埋めしたりはしない。
