# R4 AutoLab — AGENTS.md

## 1. Mission

このリポジトリの目的は、PlayStation用ゲーム『R4 -RIDGE RACER TYPE 4-』のレース処理を再現可能な方法で解析し、ゲーム速度・物理・AI・タイマーを壊さずに実描画60fps化できるかを検証するための、自動実験環境 **R4 AutoLab** を構築することである。

最優先事項は「60fpsパッチらしい値を当てること」ではない。次を証拠に基づいて解明し、自動的に反復検証できる研究装置を作ることが目的である。

* VBlank、ゲームロジック、車両物理、AI、カメラ、タイマー、描画の更新周期
* レースメインループと描画ループの呼び出し関係
* 車両状態を更新する命令と、描画時に読む命令
* フレームスキップ、待機、ダブルバッファ切り替えの実装
* 30Hz物理を保った60Hz描画、または安全な60Hzロジック化の可能性
* 各変更が速度・挙動・描画・リプレイへ与える副作用

最終目標は、同一条件から何度でも再実行でき、失敗理由を保存し、次の実験へ利用できる自動解析・自動実験基盤である。

---

## 2. Core principles

常に次の原則に従うこと。

1. **観測してから変更する。**
2. **一度の実験で変更する独立変数は原則1つ。**
3. **推測、観測事実、推論、確認済み結論を区別して記録する。**
4. **単なるエミュレーター表示上の60fpsを成功としない。**
5. **同一フレームの二重表示や動画補間を実描画60fpsと呼ばない。**
6. **物理・AI・タイマーが2倍速になった状態を失敗とする。**
7. **再現できない手動操作を解析手順に残さない。**
8. **GUIよりAPI、Lua、CLI、GDB、ログを優先する。**
9. **スクリーンショットは補助的な視覚オラクルとして使い、主要な計測値にしない。**
10. **元ファイル、ディスクイメージ、セーブデータを直接変更しない。**
11. **根拠のないアドレス総当たり、即値の一括置換、無制限探索を禁止する。**
12. **失敗実験も成果として保存し、同じ失敗を繰り返さない。**
13. **テスト不能なコードや未接続のモックだけを作って完了扱いにしない。**
14. **実装後に必ずテスト、レビュー、実行例、既知の制限を残す。**

---

## 3. Legal and asset boundaries

* ユーザーが自分で所有するゲームディスク、BIOS、セーブデータのみを対象とする。
* ROM、BIOS、実行ファイル、著作物をネットワークから取得しない。
* ゲーム本体をリポジトリへコミットしない。
* `private/`, `input/`, `states/`, `captures/raw/` はGit管理対象外にする。
* バイナリのハッシュ、アドレス、逆アセンブル、パッチ差分、解析メタデータは保存してよい。
* 元ディスクイメージへ書き込まない。初期段階はRAMパッチのみ使用する。
* 恒久パッチを作る場合も、元へ戻す手順と元バイトを必ず保存する。

---

## 4. Definition of success

### 4.1 Environment success

R4 AutoLabの初期構築完了は、次をすべて満たした状態とする。

* 1コマンドで環境診断できる。
* 1コマンドで基準実験を開始できる。
* 同じセーブステート、入力、実行時間から再現可能に起動できる。
* VBlank単位のログをJSONLまたはParquetへ保存できる。
* メモリ監視対象を設定ファイルで変更できる。
* PC、RA、主要レジスター、監視値、VBlank番号を記録できる。
* スクリーンショットとエミュレーターログを実験IDへ関連付けられる。
* RAMパッチを適用し、実験終了時に確実に復元できる。
* 基準実験と候補実験を自動比較できる。
* 実験履歴をSQLiteへ保存できる。
* クラッシュ、フリーズ、タイムアウト、異常速度を自動分類できる。
* ドライランと実機能テストが分離されている。
* 著作物がなくても単体テストと統合テスト用フェイクでCIが通る。

### 4.2 60fps research success

60fps候補は、少なくとも次を満たすまで成功扱いにしない。

* 1秒あたり58以上の異なる描画状態が観測される。
* 重複フレーム率が設定閾値以下である。
* 実時間とゲームタイマーの比率が許容範囲内である。
* 同一入力に対する車両位置、速度、RPM、方向の差が許容範囲内である。
* AI車、カウントダウン、ラップ判定が正常である。
* 画面破損、フリーズ、無効メモリアクセスがない。
* 必要なCPUオーバークロック率が記録されている。
* 少なくとも複数コース・複数視点で再検証されている。
* リプレイ互換性を未確認のまま「完全対応」と書かない。

---

## 5. Known starting evidence

次の値は公開解析由来の**出発点候補**であり、対象バージョンで再確認するまで確定情報として扱わない。

* `0x800AC064`: 約30回/秒で変化すると報告されたフレーム関連候補
* `0x800AC0D0`: プレイヤー車X座標候補
* `0x800AC0D4`: プレイヤー車Y座標候補
* `0x800AC0D8`: プレイヤー車Z座標候補
* `0x800AC104`: 車体方向候補
* `0x800AC288`: 車速候補
* `0x800AC32C`: RPM候補
* `0x801FFF58`: 車載カメラX座標候補

これらを盲目的に使用しない。最初にシリアル、実行ファイルハッシュ、ロードアドレス、実行中の値変化を確認すること。

最初の動的解析は次を優先する。

1. `0x800AC064`へのWriteを行うPCを捕捉する。
2. 車両座標へのWriteを行うPCを捕捉する。
3. 同じ座標を描画時にReadするPCを捕捉する。
4. カメラ座標へのWrite/Readを捕捉する。
5. 各発火をVBlank番号、PC、RA、SP、レジスターと結び付ける。
6. 書き込み関数から呼び出し元へ遡り、レースループ候補を作る。

---

## 6. Target architecture

次の層を分離すること。

```text
Codex / Research Agent
        |
        | structured proposal / analysis
        v
Python Supervisor
        |
        +-- Experiment state machine
        +-- Safety validator
        +-- Budget / timeout manager
        +-- Result evaluator
        +-- SQLite experiment store
        |
        +--> Emulator Adapter
        |      +-- PCSX-Redux CLI
        |      +-- Lua bridge
        |      +-- GDB / breakpoints
        |      +-- memory read/write
        |      +-- save-state control
        |      +-- GPU / VRAM capture
        |
        +--> Static Analysis Adapter
        |      +-- Ghidra Headless
        |      +-- PS-X EXE metadata
        |      +-- MIPS disassembly
        |      +-- function/call graph export
        |
        +--> Visual Oracle
        |      +-- screenshots
        |      +-- black/freeze/corruption checks
        |      +-- optional model review
        |
        +--> Artifact Store
               +-- JSONL / Parquet
               +-- screenshots
               +-- logs
               +-- patch manifests
               +-- reports
```

Codexを直接エミュレーターの無制限操作主体にしない。Python Supervisorが停止条件、安全性、再現性を管理し、Codexは仮説・解析・コード生成・次実験提案を担当する。

---

## 7. Repository layout

必要に応じて改善してよいが、責務は分離すること。

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── config/
│   ├── project.example.toml
│   ├── watch_addresses.example.toml
│   ├── success_criteria.example.toml
│   └── budgets.example.toml
├── src/r4_autolab/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── supervisor.py
│   ├── state_machine.py
│   ├── safety.py
│   ├── evaluator.py
│   ├── storage.py
│   ├── codex_client.py
│   ├── emulator/
│   │   ├── base.py
│   │   ├── pcsx_redux.py
│   │   ├── process.py
│   │   └── protocol.py
│   ├── analysis/
│   │   ├── cadence.py
│   │   ├── traces.py
│   │   ├── mips.py
│   │   ├── gpu.py
│   │   └── visual.py
│   ├── ghidra/
│   │   ├── runner.py
│   │   └── exports.py
│   └── reporting/
│       ├── markdown.py
│       └── summaries.py
├── lua/
│   ├── bootstrap.lua
│   ├── experiment_runner.lua
│   ├── breakpoints.lua
│   ├── telemetry.lua
│   ├── patching.lua
│   └── protocol.lua
├── ghidra_scripts/
├── schemas/
│   ├── experiment_proposal.schema.json
│   ├── experiment_result.schema.json
│   └── trace_event.schema.json
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── fake_emulator/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── EXPERIMENT_PROTOCOL.md
│   ├── REVERSE_ENGINEERING.md
│   ├── SUCCESS_CRITERIA.md
│   ├── SAFETY.md
│   └── DECISIONS.md
├── scripts/
│   ├── check_environment.py
│   ├── run_baseline.py
│   ├── run_experiment.py
│   └── export_report.py
├── runs/                  # gitignored
├── private/               # gitignored
├── input/                 # gitignored
├── states/                # gitignored
└── captures/raw/          # gitignored
```

---

## 8. Implementation stack

* Python 3.11以上を基本とする。
* 型ヒントを必須とし、`mypy`または`pyright`で検査できるようにする。
* `pytest`でテストする。
* CLIは`argparse`、`Typer`、`Click`のいずれかを選び、依存を増やし過ぎない。
* 設定はTOMLを基本とし、秘密情報を設定ファイルへ直書きしない。
* データモデルは`dataclass`またはPydanticを使用してよい。
* SQLiteを実験履歴の正本とする。
* 大量時系列はJSONLから開始し、必要ならParquetへ拡張する。
* 外部プロセスは引数配列で起動し、シェル文字列連結を避ける。
* すべてのプロセスにタイムアウト、終了処理、ログ回収を実装する。
* プラットフォーム依存箇所をアダプターへ隔離する。
* macOS Apple Siliconを最初の対象環境とするが、パスをハードコードしない。
* 新しい本番依存を追加するときは、目的と代替案を`docs/DECISIONS.md`へ記録する。

---

## 9. Required CLI

少なくとも次を提供すること。

```bash
r4-autolab doctor
r4-autolab init-config
r4-autolab inspect-input
r4-autolab baseline --scenario <name>
r4-autolab experiment --proposal <json>
r4-autolab compare <baseline-id> <experiment-id>
r4-autolab trace-summary <run-id>
r4-autolab report <run-id>
r4-autolab campaign --config <toml>
r4-autolab stop
```

### `doctor`

* Python、Codex CLI、PCSX-Redux、Ghidra、Java、Git、任意ツールを検出する。
* バージョンと実行パスを表示する。
* 必須・任意を区別する。
* 不足時に勝手に非公式バイナリを取得しない。
* 終了コードを適切に返す。

### `inspect-input`

* ファイル名、サイズ、SHA-256、PS-X EXEヘッダーを表示する。
* 著作物の内容をログへ大量出力しない。
* 対象バージョンを実行メタデータへ固定する。

### `campaign`

* 基準実験、候補生成、検証、比較、保存を状態機械で反復する。
* 既定はドライラン。
* 実実験には明示設定を必要とする。
* 最大実験数、最大時間、最大連続失敗、最大コストを必須設定にする。
* 中断後にSQLiteから再開できるようにする。

---

## 10. Experiment state machine

状態を明示的に実装する。

```text
CREATED
  -> VALIDATING
  -> PREPARING
  -> LAUNCHING
  -> LOADING_STATE
  -> APPLYING_PATCH
  -> RUNNING
  -> COLLECTING
  -> RESTORING
  -> EVALUATING
  -> COMPLETED

任意状態
  -> FAILED
  -> TIMED_OUT
  -> ABORTED
  -> QUARANTINED
```

各遷移をSQLiteへ記録する。クラッシュ後も`RESTORING`相当の後始末を試みる。異常終了時は次回起動前に元バイト確認を行う。

---

## 11. Emulator adapter contract

エミュレーター依存コードは抽象化し、最低限次の操作を表現する。

```python
class EmulatorAdapter(Protocol):
    def launch(self, config: LaunchConfig) -> ProcessHandle: ...
    def load_state(self, state: Path) -> None: ...
    def run_vblanks(self, count: int) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def read_memory(self, address: int, size: int) -> bytes: ...
    def write_memory(self, address: int, data: bytes) -> None: ...
    def set_breakpoint(self, spec: BreakpointSpec) -> str: ...
    def clear_breakpoint(self, breakpoint_id: str) -> None: ...
    def get_registers(self) -> RegisterSnapshot: ...
    def capture_screenshot(self, path: Path) -> None: ...
    def capture_vram(self, path: Path) -> None: ...
    def export_gpu_log(self, path: Path) -> None: ...
    def shutdown(self) -> None: ...
```

PCSX-Reduxで直接提供されない操作はLuaブリッジ、GDB、ファイルベースIPC、localhost限定ソケットの順で実装を検討する。

LuaとPython間の通信は、壊れにくい明示プロトコルにする。

* 各要求に一意ID
* JSON Lines
* request / response / eventの区別
* タイムアウト
* プロトコルバージョン
* エラーコード
* 順序番号
* 終了時flush
* 部分書き込み対策

---

## 12. Telemetry

各VBlankまたは設定周期で次を記録できるようにする。

* monotonic timestamp
* wall-clock timestamp
* experiment ID
* VBlank index
* emulated frame counter
* CPU PC
* RA
* SP
* relevant GPRs
* breakpoint cause
* accessed address
* access width
* old/new value when available
* configured memory watches
* display buffer identifier
* GPU command count or stable hash when available
* screenshot path when captured
* emulator status
* dropped-event count

監視項目は設定駆動にする。ログ量の上限、サンプリング、イベントフィルターを実装する。

秘密データやゲームバイナリ全体をログへ含めない。

---

## 13. Safe patch format

候補パッチは自由形式テキストではなく、JSON Schemaで検証する。

最低限、次を含める。

```json
{
  "id": "exp-0001",
  "hypothesis": "alternate-frame render branch",
  "target_version": {
    "serial": "unknown-until-verified",
    "executable_sha256": "..."
  },
  "changes": [
    {
      "address": "0x80000000",
      "width": 4,
      "expected_original_hex": "00000000",
      "replacement_hex": "00000000",
      "instruction_before": "unknown",
      "instruction_after": "unknown",
      "evidence": ["trace-id", "function-id"]
    }
  ],
  "predicted_effects": {
    "render_hz": 60,
    "physics_hz": 30,
    "game_speed_ratio": 1.0
  },
  "stop_conditions": [],
  "evaluation_profile": "default"
}
```

適用前に必ず以下を検証する。

* 対象ハッシュ一致
* アドレス範囲
* アラインメント
* 命令幅
* 元バイト一致
* 変更数上限
* 実行された命令か
* 過去に同一変更が失敗していないか
* 禁止領域でないか
* 復元データが存在するか

既定では1実験1変更とする。複数変更は、個別実験で各効果が確認済みの場合だけ許可する。

---

## 14. Automatic evaluation

基準実験と候補実験を次の観点で比較する。

### Timing

* VBlank数
* 実時間
* ゲームタイマー
* カウントダウン
* ラップタイム
* 倍速・低速比

### Physics

* 車両XYZ
* 速度
* RPM
* ギア
* 車体方向
* ステアリング
* ドリフト状態
* 衝突状態

### AI

* AI車の座標
* 順位
* 分岐選択
* ゴール時刻

### Rendering

* 一意なGPU状態数
* 重複フレーム率
* 表示バッファ切り替え
* GPUコマンド数
* VRAM差分
* スクリーンショット異常

### Stability

* クラッシュ
* フリーズ
* ブラック画面
* ログ停止
* 不正メモリアクセス
* タイムアウト
* エミュレータープロセス残留

閾値は`config/success_criteria.example.toml`へ外出しする。

画像だけで60fpsを判定しない。可能な限りGPU状態、バッファ、メモリ、タイミングを併用する。

---

## 15. Visual oracle

視覚解析は次の順で実装する。

1. スクリーンショット取得成功の確認
2. 画像サイズ・破損確認
3. 黒画面率
4. フレーム間差分
5. HUD固定領域の存在確認
6. 同一画像連続率
7. 極端な色・VRAM破損のヒューリスティック
8. 任意のモデルによる説明的レビュー

モデル判定は最終決定ではなく補助証拠にする。画像認識APIが未設定でも、決定論的テストが動作するようにする。

---

## 16. Static analysis

Ghidra Headlessによる再現可能な解析を優先する。

実装対象:

* PS-X EXEヘッダー解析
* ロードアドレス設定
* MIPS little-endian解析
* 関数一覧
* 基本ブロック
* 呼び出しグラフ
* 指定アドレス周辺の逆アセンブル
* xref
* 文字列
* オーバーレイ候補
* 既知アドレスと関数の対応
* JSON/CSVエクスポート

Ghidraのデコンパイル結果を正解として扱わない。delay slot、GTE、固定小数点、関数境界、オーバーレイを特に疑う。

必要な関数だけをC相当の疑似コードへ復元し、元MIPSとの対応表を残す。

完全逆コンパイルを初期目標にしない。最初は以下へ限定する。

* VBlank/同期
* レースメインループ
* 車両物理
* AI
* カメラ
* タイマー
* リプレイ
* GPUコマンド生成
* バッファ切り替え

---

## 17. Codex integration

Codex連携は交換可能なアダプターとして実装する。

初期候補:

* `codex exec`
* Codex MCP server
* OpenAI Agents SDKからCodex MCPを呼ぶ構成
* 将来的なCodex app-server

最初は最も単純で監査可能な方式を選ぶ。

Codexへ渡す情報は、巨大な生ログではなく次へ圧縮する。

* 未解決の問い
* 確認済み事実
* 主要トレース統計
* 関連命令
* 関数周辺
* 過去の候補と結果
* 使用可能な操作
* 残予算
* 成功条件

Codexの出力はJSON Schemaへ制限し、自由文から直接RAMを書き換えない。

### Codexが提案できる操作

* 追加すべき監視アドレス
* Read/Write/Execブレークポイント
* 解析すべき関数
* 取得すべきレジスター
* 1件のRAMパッチ候補
* テスト条件
* 失敗原因の分類
* 次の静的解析範囲

### Codexが直接してはいけない操作

* 未検証アドレスへの大量書き込み
* ディスクイメージ変更
* BIOS変更
* 総当たりパッチ
* 停止条件の解除
* 予算上限の変更
* 元バイト不一致を無視した適用
* 「画面が滑らかに見える」だけで成功判定
* 自分自身を無制限に再帰起動

初期開発中は、ネストした`codex exec`を実際に大量起動しない。フェイククライアントで統合テストし、明示設定がある場合だけ実Codexを使用する。

---

## 18. Campaign policy

自動キャンペーンには必ず次の上限を持たせる。

* 最大実験数
* 最大実行時間
* 最大Codex呼び出し回数
* 最大連続クラッシュ数
* 最大連続無進展数
* 最大保存容量
* APIまたは利用予算
* 1実験のVBlank上限
* 1実験の変更命令数
* 同一候補の再試行回数

停止理由を記録し、次回再開可能にする。

「進展」は次のいずれかが増えた場合とする。

* 新しい書き込み元PC
* 新しい読み出し元PC
* 新しい関数境界
* 新しい呼び出し関係
* 更新周期の確度向上
* 仮説の棄却
* 自動評価項目の改善
* 再現性の向上

単に異なるアドレスを試しただけでは進展と数えない。

---

## 19. Subagent policy

独立した読取中心の作業ではサブエージェントを使用してよい。

推奨分担:

* Emulator/API researcher
* Ghidra/MIPS researcher
* Supervisor/architecture implementer
* Test/reliability reviewer
* Documentation reviewer

ただし、同じファイルを複数エージェントが同時編集しない。主エージェントが変更を統合し、テストを実行する。

サブエージェントには巨大ログ全体を渡さず、対象範囲と期待する要約形式を指定する。

---

## 20. Testing requirements

最低限次を用意する。

### Unit tests

* 設定読み込み
* アドレス・16進数検証
* パッチ元バイト確認
* 状態遷移
* タイムアウト
* JSON Schema
* cadence分析
* 重複フレーム判定
* 実時間比
* SQLite保存
* 容量上限
* 失敗候補の重複排除

### Integration tests

* Fake Emulatorとの正常実験
* クラッシュ
* フリーズ
* 部分ログ
* 元バイト不一致
* Lua接続切断
* プロセス残留
* 中断と再開
* 基準実験との差分
* フェイクCodexによる候補生成

### Real smoke tests

私有アセットが設定されている場合のみ実行する。CIでは実行しない。

---

## 21. Documentation requirements

実装と同時に次を更新する。

### `README.md`

* 目的
* 現在できること
* できないこと
* 5分で試せるフェイクデモ
* 私有アセットを含めない設定手順
* よく使うコマンド

### `docs/ARCHITECTURE.md`

* 層構造
* プロセス境界
* データフロー
* 障害時挙動

### `docs/EXPERIMENT_PROTOCOL.md`

* 基準実験
* 候補実験
* 比較
* 復元
* 再現方法

### `docs/REVERSE_ENGINEERING.md`

* 既知アドレス
* 関数候補
* 根拠
* 確度
* 未解決事項

### `docs/DECISIONS.md`

重要な設計判断をADR風に追記する。

---

## 22. Work sequence

以下の順序で進める。単なる計画だけで停止しない。

### Phase 0: Repository audit

* 現在のファイルとGit状態を確認する。
* ユーザーの既存成果を壊さない。
* 不足情報は合理的な既定値とプレースホルダーで進める。
* `RESEARCH_PLAN.md`を作る。
* 実装前に短いアーキテクチャ方針を記録する。

### Phase 1: Safe scaffold

* Pythonプロジェクト
* `.gitignore`
* 設定例
* データモデル
* SQLite
* CLI
* fake emulator
* テスト
* `doctor`

### Phase 2: Reproducible supervisor

* 状態機械
* プロセス管理
* タイムアウト
* 実験ID
* artifacts
* baseline/candidate比較
* 中断再開

### Phase 3: PCSX-Redux bridge

* Luaブートストラップ
* IPC
* VBlankイベント
* メモリ監視
* breakpointログ
* save-stateロード
* 安全なRAMパッチ
* screenshot
* shutdown

### Phase 4: Static analysis bridge

* Ghidra検出
* headless runner
* 指定アドレス周辺export
* 関数・xref・call graph
* 解析キャッシュ

### Phase 5: Automated evaluation

* cadence
* timer ratio
* vehicle divergence
* duplicate frame
* crash/freeze
* visual checks
* report

### Phase 6: Codex research loop

* schema制約付き提案
* safety validation
* fake Codex tests
* dry-run campaign
* 明示許可時のみ実Codex
* 進展・停止ポリシー

### Phase 7: First R4 investigation

対象アセットが利用可能な場合のみ行う。

* 対象ハッシュ確認
* 既知アドレスの値変化確認
* `0x800AC064` Write PC特定
* 車両座標 Write PC特定
* 車両座標 Read PC特定
* カメラ Write/Read PC特定
* VBlank別発火周期
* 関連関数のGhidra export
* 初回解析レポート

Phase 7ではまだ60fpsパッチを目的にしない。更新構造の分類を目的とする。

---

## 23. Completion behavior

タスクを受けたら、次の行動を取る。

1. 既存リポジトリを調査する。
2. 変更前にGit差分を確認する。
3. 小さな実装単位に分ける。
4. 実装する。
5. テストする。
6. 失敗したテストを修正する。
7. 自己レビューする。
8. ドキュメントを更新する。
9. 変更概要、実行したテスト、残課題を報告する。

実装可能な範囲を残して「次はこれを作れます」で停止しない。現在の環境で実行できるところまで進める。

ただし、以下の場合は無理に進めず、明確なブロッカーとして記録する。

* 私有ゲームアセットが必要
* GUI権限が必要
* 未導入の外部アプリが必要
* OSのセキュリティ許可が必要
* 実Codex/API利用に明示設定が必要
* 非可逆操作になる

ブロッカーがあっても、フェイク、アダプター、テスト、設定例、文書化など先に完成できる作業を続ける。

---

## 24. First assignment

この`AGENTS.md`を読み込んだ直後の最初の作業は次である。

> R4 AutoLabの安全な最小実用版を構築してください。まず既存リポジトリを監査し、`RESEARCH_PLAN.md`と`docs/ARCHITECTURE.md`を作成してください。その後、Pythonパッケージ、CLI、設定、SQLite実験ストア、状態機械、Fake Emulator、パッチ検証、基準実験と候補実験の比較、テストを実装してください。次にPCSX-Redux連携の境界を定義し、実環境がなくても統合テストできるLua/IPCプロトコルとフェイクを作ってください。計画だけで停止せず、テストが通る実装まで進めてください。私有アセットや実アプリが必要な部分は明示的にスキップし、再開手順を残してください。

最初の完了報告には必ず以下を含める。

* 作成・変更したファイル
* 実装済み機能
* テスト結果
* 実行コマンド
* 実環境接続に必要なもの
* 次に自動化できる最小ステップ
* 未解決リスク
