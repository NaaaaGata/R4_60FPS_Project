# R4 AutoLab + RecompOne — AGENTS.md

## 1. この文書の位置付け

この文書は、R4 AutoLabの初期MVP構築を指示していた旧`AGENTS.md`を置き換える、2026-07-22時点の作業指示である。Phase 0〜7とrender-boundary分析は完了済みであり、同じ基盤を作り直してはならない。

次の研究トラックとして、[BlackLabelHQ/RecompOne](https://github.com/BlackLabelHQ/RecompOne)を隔離された実験用バックエンドとして評価・接続する。ただし、PCSX-ReduxとGhidraによる既存証拠を正本とし、RecompOneを正しいPS1実装または即時の60fps解決策とはみなさない。

この文書を読んだエージェントは、最初に`PROGRESS.md`、`docs/FINAL_AUDIT.md`、`docs/R4_TIMING_MODEL.md`、`docs/R4_RENDER_BOUNDARY.md`、`docs/R4_INTERPOLATION_FEASIBILITY.md`を読み、現在の確定事項と未解決事項を把握すること。

---

## 2. Mission

R4 AutoLabの次の目的は、RecompOneがR4 Japanese `SLPS-01800`の解析を次の点で前進させられるかを、再現可能かつ比較可能な方法で検証することである。

1. 既知のMIPS関数をC#へ静的変換し、制御フローとメモリアクセスを読みやすくする。
2. メイン実行ファイルとレースオーバーレイの関数境界を、既存Ghidra exportからRecompOneへ渡す。
3. 関数単位のpre/post hookと置換機構を、まず読取専用テレメトリに利用する。
4. RecompOne実行結果をPCSX-Redux基準結果と差分比較し、再コンパイル実装の忠実度を測る。
5. 忠実度が十分に確認できた場合だけ、ゲーム状態を30Hzに保ちながらC#側で描画処理を分離できるかを設計・検証する。

RecompOne上で60Hz表示が出ても、それだけではR4の実描画60fps化、PS1用60fpsパッチ、または原作挙動の再現成功とは扱わない。

---

## 3. Current verified baseline

以下は既存のPCSX-Redux/Ghidra実験で確認済みの基準である。RecompOne側の結果は必ずこの基準と比較する。

| 項目 | 確認済み結果 |
|---|---|
| 対象 | R4 Japanese `SLPS-01800` |
| PS-X EXE SHA-256 | `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775` |
| load / entry | `0x80010000` / `0x8007D4B4` |
| ループ分類 | integrated 30Hz loop |
| 正確な待機分岐 | `0x8001EC54 bne v0,zero,0x8001EC48`、delay slot `0x8001EC58 nop` |
| active / duplicate | 600 VBlankで300 / 300、完全交互 |
| レースoverlay entry | `0x80114780`、active frameのみ |
| 車両/AI dispatcher | `0x80038338`、30Hz |
| camera | `0x80034178`、30Hz |
| lap/timer | `0x8003C838`、30Hz |
| GPU submit | active frameのみ |
| 車両数 | player 1 + AI 7 |
| 既存previous/current pair | 未発見。`+0xC8/+0xCC/+0xD0`はsame-frame copy |
| render-only boundary | 未発見 |
| 現在の結論 | `RESULT_C` — current evidenceではlogic/renderが強く統合 |
| R4書き込み | render-boundary phaseでは0 |

公開候補`0x800AC064`、`0x800AC0D0/D4/D8`、`0x800AC104`、`0x800AC288`、`0x800AC32C`は、このビルドと保存状態では無効と確認済みである。これらをRecompOne上で意味のあるアドレスと仮定しない。

---

## 4. RecompOne adoption decision

### 4.1 Decision

**条件付きで採用する。** RecompOneはR4 AutoLabの代替ではなく、`experimental static-recompilation backend`として追加する。

採用対象は次である。

- PS-X EXEのMIPSからC#への変換
- CUE/ISO9660からの読取専用入力
- `funcMap`による既知関数境界の供給
- file/LBA/baseを指定したoverlay生成
- overlay dispatch tableとruntime load/unload記録
- `CpuContext`と`IMemory`を使った観測
- 関数単位のpre/post/replace hook
- GPU/VRAM、RAM read/write、関数呼出しを観測しやすくするための研究用fork

採用しないものは次である。

- RecompOneの出力をPCSX-Reduxより正しいとみなすこと
- RecompOne runtimeの固定60Hz host clockをR4の60fps成功証拠とすること
- 未確認のstub、ignored function、function replacementで強引に起動させること
- 生成C#を元ゲームの自由に再配布可能なソースコードとみなすこと
- RecompOne上の成功を、そのままPS1 RAMパッチの成功と報告すること

### 4.2 Audited upstream snapshot

初回監査で使用した上流は次である。

| 項目 | 結果 |
|---|---|
| repository | `https://github.com/BlackLabelHQ/RecompOne` |
| branch | `master` |
| pinned commit | `3d8b0e1b6ab7ebf444e8d4d02e6320746ec62807` |
| commit date | `2026-07-20T15:38:24-03:00` |
| license | MIT |
| target framework | `.NET 10` |
| local host | macOS arm64 |
| local SDK | `.NET SDK 10.0.201` |
| source build | PASS、0 errors / 4 warnings |
| CLI smoke | PASS、usage表示と終了コード1を確認 |
| R4 code generation | 未実行 |
| R4 runtime boot | 未実行 |

上流更新を自動追従しない。使用commitを設定、レポート、生成物manifestへ必ず記録する。更新時は旧commitとの差分、依存関係、生成結果、実行結果を再監査する。

### 4.3 Why it can help

RecompOneは、R4 AutoLabで不足している次の研究能力を補える可能性がある。

- 既知関数を1関数1 C# methodとして出力し、Ghidra疑似コードとは別の機械的表現を得られる。
- R4が実際に使用するoverlayを設定で分離し、同一VRAMアドレスへロードされる別コードをdispatch tableで区別できる。
- `funcMap`へaddress/name/sizeを渡せるため、Ghidraで確認済みの関数境界をlinear sweepより優先できる。
- hookから`CpuContext`と`IMemory`へアクセスでき、関数入口・出口の状態差分をRAMパッチなしで記録できる。
- runtimeと生成コードを研究用forkで変更できるため、PS1 RAMのcode caveを探す前に、外部shadow stateやrender-only再構成の成立性を試せる。
- C#側で副作用を明示的に監査でき、timer/physics/AI/audio/RNG/GPU command生成の境界を再分類できる。

### 4.4 Why it is not yet a solution

次の制約を常に明示する。

- 上流README自身が、成熟したrecompilerではなく、ゲームをbootできる段階だと説明している。
- 監査snapshotには自動テスト、release、R4向け設定例がない。
- function discovery、jump table、delay slot、indirect call、overlay認識がR4で正しいか未確認である。
- unknown instructionは生成時にコメント化される場合があり、実行経路に1件でもあれば忠実度を満たさない。
- self-modifying codeなどはfunction replacementが必要になり得る。
- BIOS、interrupt、timer、CD/XA、SPU、GPU、GTE、DMAのruntime再実装はPCSX-Reduxと同一ではない。
- PCSX `.rawstate`をRecompOneへロードできないため、同一保存状態からの直接比較は現状できない。
- runtimeはGUI中心で、headless・決定論的入力・自動shutdown・JSONL IPCは未確認である。
- host `FrameClock`は60Hz固定だが、R4が`PresentFrame`へ到達する周期や生成GPU状態の更新周期は別問題である。

---

## 5. Authority and evidence hierarchy

証拠の優先順位は次とする。

1. ハッシュ固定された所有アセット上のPCSX-Redux動的結果
2. 同じpayloadを使ったGhidra静的結果とMIPS原命令
3. RecompOneとPCSX-Reduxの一致した差分テスト
4. RecompOne生成C#のみから得た推論
5. 未実行の設計案

RecompOneだけで得た結果には必ず`RECOMP_STATIC_ONLY`または`RECOMP_RUNTIME_ONLY`を付ける。PCSX-Reduxと一致した場合だけ`CROSS_BACKEND_CONFIRMED`へ昇格できる。

RecompOneの不一致は、直ちにR4側の新事実としない。最初にfunction boundary、overlay mapping、instruction lowering、runtime hardware modelの不一致として扱う。

---

## 6. Legal, asset, and repository boundaries

1. ユーザー所有のCUE/BIN、BIOS、stateだけを使用する。
2. RecompOne source以外のゲーム資産、BIOS、実行ファイルをネットワークから取得しない。
3. CUE/BINは読取専用で開き、実行前後のSHA-256を比較する。
4. RecompOne生成C#はゲーム命令の派生表現を含むため、`private/recompone/generated/`に置き、Gitへ追加しない。
5. 抽出したPS-X EXE、overlay、RAM、VRAM、audio、screenshot rawはGitへ追加しない。
6. 公開してよいのは、ハッシュ、関数名、アドレス、短い逆アセンブル、統計、変換設定例、変換器、schema、テスト用合成fixtureである。
7. 上流sourceをvendorする場合はMIT licenseとcommit provenanceを残す。初期段階ではvendorせず、外部checkoutを環境変数で指定する。
8. `R4_AUTOLAB_RECOMPONE`はRecompOne checkoutまたはrecompiler executableの絶対パスとして扱い、秘密情報を含めない。
9. 上流source、NuGet package、mod sourceを無条件に実行しない。commit固定、source review、build log保存後にだけ使用する。
10. `.metals/`、`.vscode/`などユーザーの未追跡ファイルへ触れない。

追加するprivate/ignored候補は次である。

```text
private/recompone/
private/recompone/config/
private/recompone/function-maps/
private/recompone/generated/
private/recompone/runtime/
runs/recompone/
```

---

## 7. Architecture

RecompOneを既存経路の横に追加し、置換しない。

```text
                         +--> PCSX-Redux + Lua IPC ----> authoritative traces
R4 AutoLab Supervisor ---+
                         +--> Ghidra Headless ---------> authoritative static map
                         |
                         +--> RecompOne Adapter
                                |
                                +-- pinned upstream detector/builder
                                +-- Ghidra -> funcMap converter
                                +-- private config generator
                                +-- code-generation runner
                                +-- generated-C# compiler
                                +-- bounded runtime process
                                +-- read-only telemetry hooks
                                +-- cross-backend comparator
```

Python Supervisorがtimeout、process cleanup、asset hash、artifact path、最大ログ量、実験状態を管理する。RecompOne processへ無制限の実行権限や自動patch権限を与えない。

RecompOne固有コードは`src/r4_autolab/recompone/`へ隔離する。既存`emulator/` adapterを無理に流用せず、code generationとnative runtimeを別protocolとして表現する。

---

## 8. Required implementation phases

各phaseは、テスト、`PROGRESS.md`、設計判断、既知の制限、`git diff --check`まで完了してから次へ進む。GitHubへのcommit/pushはユーザーが依頼した場合だけ行う。

### Phase R0: Reconfirm upstream and local environment

- Git状態と既存差分を確認する。
- `AGENTS.md`で指定したupstream commitを確認する。
- `dotnet --info`を記録する。
- RecompOne sourceをprivateまたは一時checkoutでbuildする。
- build warning/error、依存restore、CLI usage、source commit、licenseを記録する。
- RecompOne sourceの取得先は指定GitHub repositoryとpinned commitに限定する。release binaryやinstallerを自動取得せず、ゲーム資産とBIOSは一切downloadしない。
- `r4-autolab doctor`へRecompOneをoptional toolとして追加する。
- PATH、`R4_AUTOLAB_RECOMPONE`、設定ファイルの順で検出する。

完了条件: assetなしのdetect/build metadataテストが通り、R4実行はまだ行わない。

### Phase R1: Adapter and configuration boundary

- shell文字列ではなく引数配列で`dotnet <recompone.dll> <config.json>`またはnative executableを起動する。
- timeout、stdout/stderr、exit code、process group cleanup、最大ログ量を実装する。
- configをtyped modelとJSON Schemaで検証する。
- `cue`、`funcMap`、overlay file/LBA/base/size、output pathのrepository escapeを拒否する。
- `linearSweep=false`を既定とする。data-as-codeの危険を理解した明示フラグなしで有効化しない。
- `patches=[]`、`stubs=[]`、`ignored=[]`を初期値とし、起動のために自動追加しない。
- private pathを公開reportでは相対化またはredactする。
- fake processで成功、timeout、partial output、unknown instruction、cleanupをテストする。

完了条件: 私有アセットなしでadapter unit/integration testが通る。

### Phase R2: Ghidra-to-RecompOne function map

- 既存`R4Export.java`のJSONからRecompOne `funcMap`を生成する。
- outputは`functions[]`と`labels[]`を持ち、各functionに`address`、`name`、正の`size`を必須とする。
- main executableと各overlayを別mapとして出力する。
- overlay baseとfile offsetを混同しない。
- overlapping function、size 0、payload外address、重複name/address、unaligned addressを拒否または明示分類する。
- Ghidraの自動境界を盲信せず、既知のrace関数とbranch metadataをfixtureで照合する。
- 出力順、名前正規化、SHA-256を決定論的にする。
- ゲーム由来byte列や生成C#をテストfixtureへ含めない。

完了条件: 合成fixtureと既存の公開可能なGhidra metadataから決定論的mapを作れる。

### Phase R3: Read-only R4 code-generation smoke

私有CUE/BINがローカル設定で利用可能な場合だけ行う。

- serial、PS-X EXE hash、load、entryを既存基準と照合する。
- CUE/BIN hashを実行前後に比較する。
- mainはGhidra function mapを使い、無根拠なlinear sweepを避ける。
- race overlayは、確認済みdisc file/offset/LBA/base/sizeとprivate function mapだけを使う。
- 初回はmainとrace overlayのcode generationだけを行い、runtimeは起動しない。
- generated C#をprivate ignored directoryへ出力する。
- unknown opcode、unmapped call候補、function count、jump table、overlay collision、生成ファイルhashをreportへ保存する。
- generated projectのcompileを行い、warning/errorを保存する。
- functionをstub/ignore/replaceしてcompileを通すことを禁止する。

完了条件: 生成とcompileが成功し、既知実行経路にunknown instructionがなく、private生成物がGit対象外である。

### Phase R4: Bounded boot fidelity

R3が成功した場合だけ行う。

- GUI権限が必要なら明確なblockerとして止める。
- Supervisorから1 processだけ起動し、二重起動を防ぐ。
- timeout、正常shutdown、例外時kill、子process残留確認を行う。
- discはread-onlyのまま使用し、memory card/settings/mod cacheをprivate run directoryへ隔離する。
- 任意modとfunction replacementを無効にする。
- boot entry、overlay event、selected function cadence、frame presentation、RAM watch、GPU display stateをbounded logへ出す。
- PCSX boot traceと、到達順・主要address・display stateを比較する。
- 音が鳴る、画面が出る、60Hzでwindowが更新されるだけでPASSにしない。

完了条件: title到達とprocess cleanupに加え、定義済みcheckpointがPCSX基準と一致する。相違は隠さず保存する。

### Phase R5: Deterministic race fidelity

R4が成功した場合だけ行う。

- PCSX `.rawstate`互換を仮定しない。
- bootからraceまでの決定論的input script、またはRecompOne専用checkpoint mechanismを別途実装する。
- checkpointは元ゲームRAMを勝手に修正する方式にしない。
- player/AI 8台、timer、camera、input、engine-speed、overlay cadence、GPU page/OT相当を同じ単位で採取する。
- 最低300 active updatesを複数fresh processで比較する。
- RecompOne内の再現性とPCSXとの差を別々に評価する。
- fixed-point、overflow、signedness、GTE、delay slotの差を優先して調査する。

完了条件: raceの主要trajectoryとcadenceが設定閾値内で一致し、差分原因が説明できる。

### Phase R6: Read-only source-level instrumentation

R5が成功した場合だけ行う。

- 最初はpre/post hookのみを使い、元functionを必ず実行する。
- hookはregister、selected memory、call order、read/write summaryだけを記録する。
- replace hook、state mutation、frame scheduling変更は禁止する。
- `IMemory` wrapperまたはcodegen instrumentationで、現在のoverlay/function/addressとmemory accessを関連付ける。
- 最大function数、最大event数、最大RAM範囲、最大run時間を設定する。
- integrated overlay内のtimer/physics/AI/camera/audio/GPU side effectを再分類する。
- 結果を同じ関数のPCSX breakpoint traceと比較する。

完了条件: 新しい依存関係または境界を、C#だけでなくMIPS/PCSXでcross-confirmできる。

### Phase R7: Render-decoupling design experiment

R6までの全gateが成功し、ユーザーが変更実験を明示許可した場合だけ行う。

- 目的は、native recompilation上でrender/logic分離が成立するかの検証であり、PS1 RAM patch作成ではない。
- 最初に全8車両、camera、orientation、discontinuity flagのexternal shadow stateを設計する。
- physics、AI、timer、input、RNG、audio、race progressionは30Hzの元functionだけが更新する。
- 中間presentationはshadow stateからtemporary render stateを作り、logic stateを変更しない。
- teleport、respawn、collision、camera switch、countdown、finish、replay、object count変更では補間をsnap/fallbackする。
- temporary stateを例外時も復元し、GPU command arenaとdisplay/draw ownershipを分離する。
- 置換対象は1実験1functionを原則とし、pre/post/replaceの差をmanifestへ記録する。
- baselineと比較してgame timer、player/AI trajectory、audio cadence、race progressionが変わらないことを確認する。
- 58以上のunique presentation states/秒、duplicate率、GPU状態、visual corruptionを測る。

RecompOne上で成功した場合の表現は`native recompilation render-decoupling prototype`とする。`PS1 60fps patch`または`original game real 60fps`とは呼ばない。

---

## 9. Fidelity gates

以下を順番に満たさない限り次へ進まない。

| Gate | 条件 | 失敗時 |
|---|---|---|
| G0 Toolchain | pinned source build、commit/license記録 | adapter作業だけ継続 |
| G1 Codegen | known path unknown opcode 0、generated compile PASS | function map/instruction loweringへ戻る |
| G2 Boot | bounded title checkpoint、cleanup、asset hash保持 | runtime fidelity issueとして保存 |
| G3 Overlay | race overlay load/base/function dispatch一致 | overlay mappingへ戻る |
| G4 Race | 8車両、timer、camera、GPU cadenceが再現 | hardware/function semanticsを調査 |
| G5 Cross-backend | PCSXとの差が閾値内または説明済み | RecompOne-only結論を禁止 |
| G6 Read-only boundary | side effectと必要inputを完全列挙 | render変更禁止 |
| G7 Mutation authorization | ユーザー明示許可とrollback設計 | 設計のみで停止 |

unknown opcode、unmapped call、無根拠stub、overlay collision、asset hash変化、process残留、ログ上限超過はFAILであり、黙ってSKIPしない。

---

## 10. Safety rules

1. 観測してから変更する。
2. RecompOne調査中もR4 RAM、disc、BIOS、save stateへ書き込まない。
3. 初期phaseではRecompOne `patches`とmod replace hookを使用しない。
4. 起動を通す目的だけのstub/ignored function追加を禁止する。
5. 1実験1独立変数を守る。
6. timeout、event cap、memory range cap、storage capを必須にする。
7. CUE/BIN hashを変更前後に確認する。
8. 同時にPCSXとRecompOneを音声付きで起動しない。比較は原則逐次実行する。
9. GUI手動操作を最終再現手順に残さない。
10. crash/freeze/black screenもartifactとして保存する。
11. 自動campaign、無制限function replacement、総当たりpatchを禁止する。
12. RecompOne runtimeのバグをR4の挙動として報告しない。

---

## 11. Required CLI direction

実装時は少なくとも次の責務を提供する。名称は既存CLIとの整合で調整してよい。

```bash
r4-autolab doctor
r4-autolab recompone-doctor
r4-autolab recompone-export-funcmap --ghidra-export <json> --output <json>
r4-autolab recompone-generate --config <json> --dry-run
r4-autolab recompone-compile --run-id <id>
r4-autolab recompone-smoke --config <private-json>
r4-autolab recompone-compare <pcsx-run-id> <recompone-run-id>
```

`recompone-generate`と`recompone-smoke`は別commandまたは明示フラグで分離する。assetなしのCIでruntime smokeを実行しない。

---

## 12. Testing requirements

### Unit tests

- upstream path/commit検出
- `.NET` version parse
- RecompOne config validation
- private/output path containment
- Ghidra -> funcMap conversion
- function overlap/size/alignment validation
- deterministic JSON/hash
- process timeout/log cap
- unknown opcode/unmapped call classification
- cross-backend cadence/trajectory comparison

### Integration tests

- fake RecompOne success
- non-zero exit
- timeout/freeze
- partial generated output
- malformed JSON
- unknown instruction log
- child process cleanup
- asset hash mismatch refusal
- generated path Git-exclusion check

### Real smoke tests

私有アセットと明示設定がある場合だけ実行し、CIではSKIPする。R4 code generation、generated compile、runtime boot、race fidelityを別test markerへ分離する。

既存`pytest`、`mypy src`、`r4-autolab doctor`、PCSX capabilityを壊してはならない。

---

## 13. Documentation and reporting

実装と同時に次を更新する。

- `PROGRESS.md`: phase、commit、command、PASS/FAIL/SKIP、artifact
- `docs/DECISIONS.md`: RecompOneを補助backendとして採用した理由
- `docs/RECOMPONE_COMPATIBILITY.md`: upstream commit、build、R4 codegen/runtime結果
- `docs/RECOMPONE_FIDELITY.md`: PCSXとの差分と証拠level
- `docs/ARCHITECTURE.md`: 新process境界とprivate artifacts
- `.gitignore`: generated/asset/runtime private paths
- `README.md`: experimentalであること、できること、できないこと

各real run reportには最低限次を含める。

- RecompOne commitとsource tree dirty状態
- .NET SDK/runtime、OS、architecture
- target serial、executable hash、overlay hash/base/source
- config hashとfunction-map hash
- command引数（private pathはredact）
- start/end time、timeout、exit code、process cleanup
- generated function数、unknown opcode、unmapped call、stub/ignored/patch count
- CUE/BIN before/after hash
- PCSX baseline run ID
- cadence、trajectory、timer、GPU/display差分
- evidence classification

---

## 14. Upstream contribution policy

R4固有asset、生成C#、overlay binary、固有のprivate pathを上流issue/PRへ送らない。

RecompOne一般の再現可能なbugを見つけた場合は、ゲーム由来byteを含まない最小合成fixtureで再現する。上流へ変更を送る場合はユーザーの明示依頼を得て、MIT license、coding style、作者の方針を尊重する。

R4 AutoLab内で研究用fork差分を持つ場合は、上流commit、patch file、目的、rollback、upstreamabilityを記録する。巨大なforkをこのrepositoryへ無説明でコピーしない。

---

## 15. Immediate next assignment

この`AGENTS.md`を読んだ次の実装エージェントは、いきなりR4をRecompOneで起動したり60fps変更を行ってはならない。次を順に最後まで行う。

1. repository、Git差分、既存テストを監査する。
2. `PROGRESS.md`と主要な最終audit文書を読む。
3. Phase R0のupstream commit、license、.NET、buildを再確認する。
4. `docs/RECOMPONE_COMPATIBILITY.md`とADRを作る。
5. optional RecompOne detectorを`doctor`へ追加する。
6. typed config、safe process runner、fake RecompOne testを実装する。
7. Ghidra exportからRecompOne `funcMap`への決定論的converterとschema/testを実装する。
8. private pathとgenerated outputのGit除外を確認する。
9. `pytest`、`mypy src`、`r4-autolab doctor`、`git diff --check`を実行する。
10. 私有CUE/BINが設定済みなら、Phase R3のcode-generation dry-runとcompileまで行う。runtime bootは別gateとする。
11. 変更ファイル、build結果、test結果、R4 codegen結果、unknown機能、次gateを報告する。

Phase R0〜R3ではR4 memory write、function replacement、PS1 patch、frame-wait変更、60fps実験を行わない。

---

## 16. Completion report

完了報告には次を含める。

1. 変更したファイル
2. RecompOne repository/commit/license
3. .NET/OS/architecture
4. upstream buildとwarning/error
5. 実装したadapter/config/funcMap機能
6. private assetの使用有無
7. R4 code generationとgenerated compile結果
8. unknown opcode/unmapped call/stub/ignored/patch数
9. CUE/BIN hash保持
10. 実行したtestsと結果
11. process残留の有無
12. PCSX基準と比較できた項目
13. 未確認機能と正確なblocker
14. 現在通過したfidelity gate
15. RecompOneが研究を前進させた具体的証拠
16. 次の安全な最小step
17. `git diff --check`結果

R4 runtime bootに失敗しても、再現ログ、原因分類、converter、adapter、tests、再開手順が完成していれば、その範囲を成果として記録する。失敗を隠すためにstub、ignored function、replacement、safety bypassを追加してはならない。
